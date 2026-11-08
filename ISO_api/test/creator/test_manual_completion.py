from copy import deepcopy
import pytest
from fastapi.testclient import TestClient

from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.schemas.creator_manual import ManualToolRequest, ManualNcRequest
from src.schemas.creator_manual_completion import ManualCompletionRequest
from src.services.creator.cam import CamInputError
from src.services.creator.manual import prepare_tool, values_for, confirm_nc, operation_for
from src.services.creator.manual_completion import complete_manual
from src.services.creator.preview import preview_assets
from test_manual import base, common, step, completed


def incomplete():
    created = prepare_tool(ManualToolRequest(**common(base(b'T1 M6\nG1 X1\nM30\n')), name='Empty tool', toolTypeId='MillingCuttingTool', values={}))
    added = step(created['draft'], created['assetNodeId'])
    return added['draft'], created['assetNodeId'], added['stepNodeId']


def request(draft, **kwargs):
    return ManualCompletionRequest(**common(draft), workplanNodeId='wp', includePlaceholders=True, **kwargs)


def test_manual_placeholders_match_13399_and_xml_reports():
    draft, asset, step_id = incomplete()
    before = deepcopy(draft)
    result = complete_manual(request(draft))
    assert draft == before and result['addedCount'] > 0
    filled = result['draft']
    assert filled['revision'] == draft['revision'] + 1
    assert not filled['ncReviews']
    assert values_for(filled, asset)['effective_cutting_diameter'] == 0
    tool_review = preview_assets(CreatorDraft.model_validate(filled), [asset])
    assert any(w['code'] == 'AUTHORING_PLACEHOLDER' for w in tool_review['warnings'])
    assert not preview_assets(CreatorDraft.model_validate(filled), ['root'])['valid']
    confirmed = confirm_nc(ManualNcRequest(**common(filled), workplanNodeId='wp', fileId='original', acknowledged=True,
        reason='T and intervals checked', assignments=[dict(stepNodeId=step_id, toolTag='T1', lineStart=1, lineEnd=3)]), b'T1 M6\nG1 X1\nM30\n')['draft']
    review = preview_assets(CreatorDraft.model_validate(confirmed), ['root'])
    assert review['valid'] and not review['machineReady'] and not review['finalizable']
    assert any(w['code'] == 'AUTHORING_PLACEHOLDER' for w in review['warnings'])
    assert preview_assets(CreatorDraft.model_validate(confirmed), [asset])['valid']
    assert complete_manual(request(confirmed))['draft'] == confirmed


def test_existing_values_zero_false_and_confirmation_are_preserved_when_unchanged():
    draft, _, asset = completed()
    before = deepcopy(draft)
    assert complete_manual(request(draft))['draft'] == before
    assert values_for(draft, asset)['effective_cutting_diameter'] == 10
    assert any(n['fields'].get('inhibit_spindle_override') is False for n in draft['nodes'].values())


def test_targeted_completion_keeps_other_step_unchanged_except_shared_tool_missing_values():
    draft, asset, first = incomplete()
    second = step(draft, asset, name='Second')
    draft = second['draft']
    op = operation_for(draft, first)
    tool_id = op['fields']['its_tool']['$node']
    draft['nodes'][tool_id]['fields']['effective_cutting_diameter'] = 12
    before = deepcopy(draft)
    result = complete_manual(request(draft, stepNodeIds=[second['stepNodeId']]))['draft']
    assert values_for(result, asset)['effective_cutting_diameter'] == 12
    assert result['nodes'][first] == before['nodes'][first]
    assert result['nodes'][tool_id]['fields']['effective_cutting_diameter'] == 12
    assert 'its_secplane' not in result['nodes'][first]['fields']


def test_conflicting_existing_internal_values_fail_without_mutating():
    draft, asset, first = incomplete()
    second = step(draft, asset, name='Second')
    draft = second['draft']
    for step_id, diameter in [(first, 12), (second['stepNodeId'], 14)]:
        tool_id = operation_for(draft, step_id)['fields']['its_tool']['$node']
        draft['nodes'][tool_id]['fields']['effective_cutting_diameter'] = diameter
    before = deepcopy(draft)
    with pytest.raises(CamInputError, match='제원이 다릅니다'):
        complete_manual(request(draft))
    assert draft == before


def test_http_new_endpoint_and_opt_out_preserve_legacy_contract():
    draft, asset, _ = incomplete()
    client = TestClient(app)
    payload = request(draft).model_dump(by_alias=True)
    payload['includePlaceholders'] = False
    response = client.post('/api/v3/creator/workplans/manual-complete', json=payload)
    assert response.status_code == 200, response.text
    assert 'effective_cutting_diameter' not in values_for(response.json()['draft'], asset)
    payload['expectedRevision'] += 1
    assert client.post('/api/v3/creator/workplans/manual-complete', json=payload).status_code == 422
