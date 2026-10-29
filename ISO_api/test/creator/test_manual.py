import copy
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket
from xsdata.formats.dataclass.parsers import XmlParser
from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.schemas.creator_manual import ManualToolRequest, ManualStepRequest, ManualNcRequest
from src.schemas.creator_completion import CompletionRequest
from src.services.creator.manual import manual_profile, prepare_tool, prepare_step, confirm_nc, values_for
from src.services.creator.completion import complete_workplan
from src.services.creator.preview import preview_assets
from src.services.creator.nc import analyze_nc, to_graph, compile_tools
from src.services.creator.schema_provider import get_model, get_profile, policy_hash
from src.services.creator.cam import CamInputError
from test_nc import fixture, NC


def base(data=NC):
    draft = fixture().draft.model_dump(by_alias=True)
    draft['fileLinks'][0]['sha256'] = hashlib.sha256(data).hexdigest()
    draft['nodes']['wp']['fields']['its_elements'] = []
    draft['nodes']['project']['fields']['its_id'] = 'manual-project'
    for prefix in ('s', 'o', 't'):
        for i in range(3):
            del draft['nodes'][f'{prefix}{i}']
    draft['nodes']['file']['fields'].update(schema_version='v31', asset_kind='instance', asset_global_id='https://example.test/global')
    return draft


def common(draft):
    return dict(draft=draft, expectedRevision=draft['revision'], profileHash=manual_profile()['hash'])


def tool(draft, name='EM10', **extra):
    return prepare_tool(ManualToolRequest(**common(draft), name=name, toolTypeId='MillingCuttingTool',
        values={'effective_cutting_diameter': {'value': 10, 'unit': 'mm'}, 'assembly_length': {'value': 50, 'unit': 'mm'},
                'maximum_depth_of_cut': {'value': 2, 'unit': 'mm'}, 'number_of_teeth': {'value': 2, 'unit': '1'}}, **extra))


def step(draft, asset, name='WS1'):
    return prepare_step(ManualStepRequest(**common(draft), action='add', workplanNodeId='wp', name=name, operationTypeId='FreeformOperation', assetNodeId=asset))


def completed(data=b'T1 M6\nG1 X1\nM30\n'):
    created = tool(base(data)); asset = created['assetNodeId']
    added = step(created['draft'], asset)
    result = complete_workplan(CompletionRequest(draft=added['draft'], workplanNodeId='wp', includePlaceholders=True))
    draft = result['draft']
    req = ManualNcRequest(**common(draft), workplanNodeId='wp', fileId='original', acknowledged=True, reason='NC 원문과 가공 순서 확인', assignments=[{'stepNodeId': added['stepNodeId'], 'toolTag': 'T01', 'lineStart': 1, 'lineEnd': len(data.splitlines())}])
    return confirm_nc(req, data)['draft'], req, asset


def test_tool_creation_without_cam_or_nc_and_units_roundtrip():
    draft = base(); before = copy.deepcopy(draft)
    result = tool(draft)
    assert draft == before and result['persisted'] is False
    review = preview_assets(CreatorDraft.model_validate(result['draft']), [result['assetNodeId']])
    assert review['valid'], review['issues']
    assert '<unit_name>mm</unit_name>' in review['artifacts'][0]['xml']
    assert 'assembly_length' in review['artifacts'][0]['xml']
    assert 'overhang_length' not in review['artifacts'][0]['xml']
    XmlParser().from_string(review['artifacts'][0]['xml'], get_model().DtAsset)


def test_manual_project_xml_and_non_t_identity():
    draft, _, asset = completed()
    assert draft['ncReviews'][0]['manual']['mode'] == 'manual'
    assert draft['toolLinks'][0]['toolTag'] == 'T1'
    aid = next(a for a in draft['assets'] if a['assetNodeId'] == asset)
    assert draft['nodes'][aid['elementNodeId']]['fields']['element_id'] != 'T1'
    for item in draft['assets']:
        review = preview_assets(CreatorDraft.model_validate(draft), [item['assetNodeId']])
        assert review['valid'], (item['role'], review['issues'])
    review = preview_assets(CreatorDraft.model_validate(draft), ['root'])
    assert any(w['code'] == 'NC_MANUAL_CONFIRMATION' for w in review['warnings'])
    assert 'ref_dt_cutting_tool' in review['artifacts'][0]['xml']


def test_unsupported_nc_manual_confirmation_preserves_warning():
    draft, _, _ = completed(b'T1 M6\nM98 P123\nM30\n')
    assert draft['ncReviews'][0]['manual']['analyzerSupported'] is False
    assert preview_assets(CreatorDraft.model_validate(draft), ['root'])['valid']


@pytest.mark.parametrize('change', ['values', 'file', 'order', 'rows', 'tag', 'encoding', 'identity'])
def test_manual_confirmation_is_invalidated(change):
    draft, _, asset = completed()
    if change == 'values':
        draft['nodes'][next(n for n in draft['nodes'] if draft['nodes'][n]['typeId'] == 'MillingCuttingTool')]['fields']['effective_cutting_diameter'] = 99
    elif change == 'file': draft['fileLinks'][0]['sha256'] = '0' * 64
    elif change == 'order': draft['nodes']['wp']['fields']['its_elements'].append(copy.deepcopy(draft['nodes']['wp']['fields']['its_elements'][0]))
    elif change == 'rows': draft['ncReviews'][0]['manual']['assignments'][0]['lineStart'] = 2
    elif change == 'tag': draft['toolLinks'][0]['toolTag'] = 'T2'
    elif change == 'encoding': draft['ncReviews'][0]['manual']['encoding'] = 'cp949'
    else: draft['nodes'][asset]['fields']['id'] = 'renamed'
    assert not preview_assets(CreatorDraft.model_validate(draft), ['root'])['valid']


def test_sync_requires_explicit_confirmation_and_does_not_mutate():
    draft, _, asset = completed()
    toolnode = next(n for n in draft['nodes'].values() if n['typeId'] == 'MillingCuttingTool')
    toolnode['fields']['effective_cutting_diameter'] = 22
    before = copy.deepcopy(draft)
    with pytest.raises(CamInputError, match='동기화'):
        tool(draft, assetNodeId=asset)
    assert draft == before
    result = tool(draft, assetNodeId=asset, synchronize=True)
    assert result['draft']['nodes'][toolnode['nodeId']]['fields']['effective_cutting_diameter'] == 10
    assert not preview_assets(CreatorDraft.model_validate(result['draft']), ['root'])['valid']


def test_duplicate_t_different_tool_and_invalid_ranges_are_rejected():
    data = b'T1 M6\nG1 X1\nT1 M6\nM30'
    a = tool(base(data)); b = tool(a['draft'], 'second')
    s1 = step(b['draft'], a['assetNodeId'], 'A'); s2 = step(s1['draft'], b['assetNodeId'], 'B')
    rows = [dict(stepNodeId=s1['stepNodeId'], toolTag='T1', lineStart=1, lineEnd=2), dict(stepNodeId=s2['stepNodeId'], toolTag='T1', lineStart=3, lineEnd=4)]
    req = ManualNcRequest(**common(s2['draft']), workplanNodeId='wp', fileId='original', acknowledged=True, reason='test', assignments=rows)
    with pytest.raises(CamInputError, match='같은 공구'): confirm_nc(req, data)
    req.assignments[1].lineStart = 2
    with pytest.raises(CamInputError, match='구간'): confirm_nc(req, data)
    req.assignments[1].lineStart = 1
    req.assignments[1].lineEnd = 2
    req.assignments[1].toolTag = 'T2'
    with pytest.raises(CamInputError, match='같은 T'): confirm_nc(req, data)


def test_legacy_cam_conversion_is_explicit_and_preserves_nodes():
    draft = compile_tools(fixture(), NC)['draft']
    before = copy.deepcopy(draft)
    asset = draft['toolLinks'][0]['assetNodeId']
    request = ManualStepRequest(**common(draft), action='assign', workplanNodeId='wp', stepNodeId='s0', assetNodeId=asset)
    with pytest.raises(CamInputError, match='전환'): prepare_step(request)
    assert draft == before
    request.adoptExisting = True
    result = prepare_step(request)['draft']
    assert result['nodes'] == before['nodes']
    assert result['assets'] == before['assets']
    assert len(result['manualToolLinks']) == 3
    assert len(result['manualTools']) == 2
    analysis = analyze_nc(NC, 'original')
    rows = [dict(stepNodeId=f's{i}', toolTag=e['toolTag'], lineStart=e['lineStart'], lineEnd=e['lineEnd']) for i, e in enumerate(analysis['events'])]
    confirmed = confirm_nc(ManualNcRequest(**common(result), workplanNodeId='wp', fileId='original', acknowledged=True, reason='기존 CAM 연결 유지', assignments=rows), NC)['draft']
    assert confirmed['nodes'] == before['nodes']
    assert confirmed['toolLinks'] == before['toolLinks']


def test_duplicate_tool_identity_rejected_by_server():
    draft, _, asset = completed()
    second = tool(draft, 'second')['draft']
    old = next(a for a in second['assets'] if a['assetNodeId'] == asset)
    new = second['assets'][-1]
    second['nodes'][new['assetNodeId']]['fields']['id'] = second['nodes'][asset]['fields']['id']
    second['nodes'][new['elementNodeId']]['fields']['element_id'] = second['nodes'][old['elementNodeId']]['fields']['element_id']
    review = preview_assets(CreatorDraft.model_validate(second), ['root'])
    assert any('중복' in issue['message'] for issue in review['issues'])


def test_drill_angle_and_unit_roundtrip():
    created = prepare_tool(ManualToolRequest(**common(base()), name='drill', toolTypeId='TwistDrill', values={'point_angle': {'value': 118, 'unit': 'deg'}}))
    added = prepare_step(ManualStepRequest(**common(created['draft']), action='add', workplanNodeId='wp', name='drill', operationTypeId='Drilling', assetNodeId=created['assetNodeId']))
    internal = next(n for n in added['draft']['nodes'].values() if n['typeId'] == 'TwistDrill')
    assert internal['fields']['point_angle'] == 118
    assert values_for(added['draft'], created['assetNodeId'])['point_angle'] == 118


def test_manual_api_strict_validation_and_no_persistence(monkeypatch):
    spies = []
    for owner, method in [(AsyncIOMotorCollection, 'insert_one'), (AsyncIOMotorCollection, 'update_one'), (AsyncIOMotorCollection, 'delete_one'), (AsyncIOMotorGridFSBucket, 'upload_from_stream')]:
        spy = AsyncMock(side_effect=AssertionError('No writes'))
        monkeypatch.setattr(owner, method, spy); spies.append(spy)
    with TestClient(app) as client:
        payload = dict(**common(base()), name='manual', toolTypeId='MillingCuttingTool', values={'effective_cutting_diameter': {'value': 1, 'unit': 'in'}})
        response = client.post('/api/v3/creator/tools/prepare', json=payload)
        assert response.status_code == 200, response.text
        result = response.json()
        assert values_for(result['draft'], result['assetNodeId'])['effective_cutting_diameter'] == 25.4
        payload['values']['effective_cutting_diameter']['value'] = True
        assert client.post('/api/v3/creator/tools/prepare', json=payload).status_code == 422
        assert client.post('/api/v3/creator/nc/confirm', data={'payload': '{}'}).status_code == 422
        draft, request, _ = completed()
        response = client.post('/api/v3/creator/nc/confirm', data={'payload': request.model_dump_json(by_alias=True)}, files={'file:original': ('manual.nc', b'T1 M6\nG1 X1\nM30\n')})
        assert response.status_code == 200, response.text
        assert response.json()['persisted'] is False
    for spy in spies: spy.assert_not_called()


def test_kimm_nc_only_eight_steps_four_tools_eight_xml(monkeypatch):
    directory = Path(os.environ.get('KIMM_DATA_DIR', '/data/xml/기계연'))
    if not directory.exists(): pytest.skip('KIMM_DATA_DIR unavailable')
    folder = next(p for p in directory.iterdir() if p.is_dir() and p.name.startswith('1'))
    nc = (folder / 'merge.tap').read_bytes()
    analysis = analyze_nc(nc, 'original', 'cp949')
    draft = base(nc)
    tools = {}
    for tag in dict.fromkeys(e['toolTag'] for e in analysis['events']):
        # Explicit authoring fixture values, not dimensions inferred from the NC.
        result = tool(draft, f'{tag} 시험 공구'); draft = result['draft']; tools[tag] = result['assetNodeId']
    assignments = []
    for i, event in enumerate(analysis['events']):
        result = step(draft, tools[event['toolTag']], f'작업 {i+1}'); draft = result['draft']
        assignments.append(dict(stepNodeId=result['stepNodeId'], toolTag=event['toolTag'], lineStart=event['lineStart'], lineEnd=event['lineEnd']))
    draft = complete_workplan(CompletionRequest(draft=draft, workplanNodeId='wp', includePlaceholders=True))['draft']
    for role, name in [('machine', '기계연_machine_tool.xml'), ('material', '기계연_material.xml')]:
        ref = to_graph(XmlParser().from_string((directory / name).read_text(), get_model().DtAsset), draft['nodes'])
        aid = ref['$node']; eid = draft['nodes'][aid]['fields']['dt_elements'][0]['$node']
        draft['assets'].append(dict(assetNodeId=aid, elementNodeId=eid, role=role))
    draft = confirm_nc(ManualNcRequest(**common(draft), workplanNodeId='wp', fileId='original', encoding='cp949', acknowledged=True, reason='기계연 NC 순서 수동 인수 시험', assignments=assignments), nc)['draft']
    # Derived machine/material references must not invalidate the authored NC snapshot.
    draft['referencePolicyHash'] = policy_hash()
    for policy in get_profile().referencePolicies:
        if policy.targetRole not in ('machine', 'material'):
            continue
        asset = next(a for a in draft['assets'] if a['role'] == policy.targetRole)
        sources = ['wp'] if policy.targetRole == 'machine' else [n['nodeId'] for n in draft['nodes'].values() if n['typeId'] == 'Workpiece']
        for source in sources:
            draft['referenceLinks'].append(dict(policyId=policy.id, sourceNodeId=source, targetAssetNodeId=asset['assetNodeId']))
    assert len(draft['assets']) == 8 and len(draft['toolLinks']) == 4
    for a in draft['assets']:
        review = preview_assets(CreatorDraft.model_validate(draft), [a['assetNodeId']])
        assert review['valid'], (a['role'], review['issues'])
        XmlParser().from_string(review['artifacts'][0]['xml'], get_model().DtAsset)
