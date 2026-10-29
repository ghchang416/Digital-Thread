import copy
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket

from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.schemas.creator_completion import CompletionRequest
from src.services.creator.completion import complete_workplan
from src.services.creator.cam import CamInputError, parse_cam
from src.services.creator.preview import preview_assets
from src.services.creator.completion_warnings import completion_warnings
from test_cam import request as cam_request, encoded, power
from test_nc import fixture, NC
from src.services.creator.nc import compile_tools


def request(**kwargs):
    draft = fixture().draft.model_dump(by_alias=True)
    # No file or NC references are fabricated by this service.
    draft['assets'] = draft['assets'][:1]
    draft['fileLinks'] = []
    draft['nodes']['project']['fields']['its_id'] = 'Project'
    parsed = parse_cam(cam_request(ids=['one', 'two']), {'one': ('a.json', encoded(power('A'))), 'two': ('b.json', encoded(power('B')))})
    draft['nodes']['wp']['fields']['its_elements'] = []
    for op in parsed['operations']:
        draft['nodes'].update(op['nodes'])
        draft['nodes']['wp']['fields']['its_elements'].append({'$node': op['rootNodeId']})
    # Remove disconnected fixture steps, which would count as other owners.
    for id in ['s0', 's1', 's2', 'o0', 'o1', 'o2', 't0', 't1', 't2']:
        del draft['nodes'][id]
    return CompletionRequest(draft=draft, workplanNodeId='wp', **kwargs)


def test_missing_only_preserves_cam_zero_false_and_is_idempotent():
    req = request(includePlaceholders=True)
    before = req.model_dump(by_alias=True)
    result = complete_workplan(req)
    assert req.model_dump(by_alias=True) == before
    assert result['addedCount'] > 0 and not result['persisted'] and not result['machineReady']
    for id, node in before['draft']['nodes'].items():
        for field, value in node['fields'].items():
            assert result['draft']['nodes'][id]['fields'][field] == value
    completed = CreatorDraft.model_validate(result['draft'])
    review = preview_assets(completed, ['root'])
    assert review['valid'], review['issues']
    assert review['warnings'] and not review['finalizable']
    assert 'completionEntries' not in review['artifacts'][0]['xml']
    assert 'authoring-template' not in review['artifacts'][0]['xml']
    again = complete_workplan(req.model_copy(update={'draft': completed}))
    assert again['addedCount'] == 0 and again['draft'] == result['draft']


def test_defaults_only_does_not_invent_geometry_or_required_numbers():
    req = request()
    result = complete_workplan(req)
    assert all(entry['kind'] != 'placeholder' for entry in result['draft']['completionEntries'])
    for ref in result['draft']['nodes']['wp']['fields']['its_elements']:
        assert 'its_secplane' not in result['draft']['nodes'][ref['$node']]['fields']
    assert not preview_assets(CreatorDraft.model_validate(result['draft']), ['root'])['valid']


def test_batch_overrides_only_missing_values_and_changes_still_warn():
    result = complete_workplan(request(includePlaceholders=True, overrides={'maximum_depth_of_cut': 2.5, 'feedrate_reference': 'ccp', 'coolant': True, 'security_plane_z': 50}))
    entries = result['draft']['completionEntries']
    assert len([e for e in entries if e['fieldName'] == 'maximum_depth_of_cut' and e['value'] == 2.5 and e['kind'] == 'batch']) == 2
    assert not any(e['fieldName'] == 'coolant' for e in entries)  # CAM false survives true override.
    assert len([e for e in entries if e['fieldName'] == 'coordinates' and e['value'][-1]['value'] == 50]) == 2
    draft = CreatorDraft.model_validate(result['draft'])
    entry = next(e for e in draft.completionEntries if e.fieldName == 'maximum_depth_of_cut')
    draft.nodes[entry.nodeId].fields[entry.fieldName] = 8
    assert any('보완 후 변경됨' in w['message'] for w in completion_warnings(draft, ['root']))
    assert completion_warnings(draft, ['file']) == []


@pytest.mark.parametrize('overrides', [{'maximum_depth_of_cut': -1}, {'feedrate_reference': 'bad'}, {'coolant': 'false'}, {'unknown': 1}, {'maximum_depth_of_cut': True}])
def test_invalid_overrides_rejected_even_if_unused(overrides):
    with pytest.raises(CamInputError):
        complete_workplan(request(overrides=overrides))


def test_unknown_operation_not_guessed_and_other_workplans_preserved():
    req = request(includePlaceholders=True)
    step = req.draft.nodes['wp'].fields['its_elements'][0].node
    del req.draft.nodes[step].fields['its_operation']
    before = copy.deepcopy(req.draft.nodes['file'])
    result = complete_workplan(req)
    assert 'its_operation' not in result['draft']['nodes'][step]['fields']
    assert CreatorDraft.model_validate(result['draft']).nodes['file'] == before
    assert not any(e['fieldName'] in ('ref_dt_cutting_tool', 'ref_dt_file') for e in result['draft']['completionEntries'])


def test_shared_other_workplan_nodes_are_not_modified():
    req = request(includePlaceholders=True)
    step = req.draft.nodes['wp'].fields['its_elements'][0].node
    other = req.draft.nodes[step].model_copy(deep=True, update={'nodeId': 'other'})
    req.draft.nodes['other'] = other
    shared_op = other.fields['its_operation'].node
    before = req.draft.nodes[shared_op].model_dump(by_alias=True)
    result = complete_workplan(req)
    assert result['draft']['nodes'][shared_op] == before
    assert result['skipped']
    req.draft.nodes['wp2'] = req.draft.nodes['wp'].model_copy(deep=True, update={'nodeId': 'wp2'})
    with pytest.raises(CamInputError, match='다른 워크플랜'):
        complete_workplan(req)


def test_existing_plane_keeps_coordinates_and_applies_z_only_when_position_missing():
    req = request(includePlaceholders=True, overrides={'security_plane_z': 30})
    result = complete_workplan(req)
    req.draft = CreatorDraft.model_validate(result['draft'])
    again = complete_workplan(req.model_copy(update={'overrides': {'security_plane_z': 100}}))
    assert again['addedCount'] == 0
    assert again['draft'] == result['draft']
    step = req.draft.nodes['wp'].fields['its_elements'][0].node
    plane = req.draft.nodes[step].fields['its_secplane'].node
    del req.draft.nodes[plane].fields['position']
    changed = complete_workplan(req)
    position = changed['draft']['nodes'][plane]['fields']['position']['$node']
    location = changed['draft']['nodes'][position]['fields']['location']['$node']
    assert changed['draft']['nodes'][location]['fields']['coordinates'][-1]['value'] == 30


def test_tool_asset_preview_keeps_source_workingstep_warnings():
    nc = fixture()
    completed = complete_workplan(CompletionRequest(draft=nc.draft, workplanNodeId='wp', includePlaceholders=True))
    nc.draft = CreatorDraft.model_validate(completed['draft'])
    linked = compile_tools(nc, NC)
    assert linked['ready']
    draft = CreatorDraft.model_validate(linked['draft'])
    tools = [asset.assetNodeId for asset in draft.assets if asset.role == 'tool']
    review = preview_assets(draft, tools)
    assert review['valid'], review['issues']
    assert review['warnings']
    assert any(warning['fieldName'] == 'overall_assembly_length' for warning in review['warnings'])


def test_api_no_persistence(monkeypatch):
    spies = []
    for owner, method in [(AsyncIOMotorCollection, 'insert_one'), (AsyncIOMotorCollection, 'update_one'), (AsyncIOMotorGridFSBucket, 'upload_from_stream')]:
        spy = AsyncMock(side_effect=AssertionError('Write forbidden'))
        monkeypatch.setattr(owner, method, spy)
        spies.append(spy)
    with TestClient(app) as client:
        response = client.post('/api/v3/creator/workplans/complete', json=request(includePlaceholders=True).model_dump(by_alias=True))
        assert response.status_code == 200, response.text
        assert response.json()['addedCount'] > 0
    for spy in spies:
        spy.assert_not_called()
