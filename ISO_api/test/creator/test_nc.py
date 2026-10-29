import copy
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket

from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.schemas.creator_nc import NcToolsRequest
from src.services.creator.cam import CamInputError
from src.services.creator.catalog import get_catalog
from src.services.creator.nc import analyze_nc, compile_tools, tool_values
from src.services.creator.references import resolve_references
from src.services.creator.preview import preview_assets

NC = b'T1 M6\nG1 X1\nT2 M6\nG1 X2\nT1 M6\nM30\n'


def fixture(data=NC):
    nodes = {}

    def node(node_id, type, **fields):
        nodes[node_id] = {"nodeId": node_id, "typeId": type, "fields": fields}
        return {"$node": node_id}

    steps = [node(f's{i}', 'MachiningWorkingstep', its_id=f'operation_{i}', its_operation=node(
        f'o{i}', 'BottomAndSideRoughMilling', its_tool=node(f't{i}', 'MillingCuttingTool', its_id=f'tool_{i}',
        effective_cutting_diameter=10 if i != 1 else 6, number_of_effective_teeth=2))) for i in range(3)]
    project = node('project', 'DtProject', element_id='project', main_workplan=node('wp', 'Workplan', its_id='WP1', its_elements=steps))
    node('root', 'DtAsset', asset_global_id='https://example.test/global', id='job', schema_version='v31', asset_kind='instance', dt_elements=[project])
    node('file', 'DtAsset', id='nc', dt_elements=[node('file-element', 'DtFile', element_id='nc', category='NC', content_type='text/x-gcode', path='test.nc')])
    catalog = get_catalog()
    analysis = analyze_nc(data, 'original')
    draft = CreatorDraft(schemaHash=catalog['schemaHash'], rulesVersion=catalog['rulesVersion'], draftId='draft', revision=0,
        nodes=nodes, assets=[{'assetNodeId': 'root', 'elementNodeId': 'project', 'role': 'project'},
                            {'assetNodeId': 'file', 'elementNodeId': 'file-element', 'role': 'file'}], projectAssetNodeId='root',
        fileLinks=[{'assetNodeId': 'file', 'fileId': 'original', 'sha256': analysis['sha256'], 'purpose': 'NC', 'workplanNodeId': 'wp'}])
    request = NcToolsRequest(fileId='original', draft=draft, workplanNodeId='wp', fileAssetNodeId='file',
        assignments=[{'stepNodeId': f's{i}', 'eventId': event['eventId']} for i, event in enumerate(analysis['events'])])
    return request


def test_same_t_reuses_asset_and_legacy_xml_reference():
    request = fixture()
    original = request.model_dump()
    result = compile_tools(request, NC)
    assert result['ready'] and not result['persisted']
    assert request.model_dump() == original
    draft = CreatorDraft.model_validate(result['draft'])
    assert len(draft.toolLinks) == 2
    assert draft.toolLinks[0].stepNodeIds == ['s0', 's2']
    tools = [a.assetNodeId for a in draft.assets if a.role == 'tool']
    preview = preview_assets(draft, tools)
    assert preview['valid'], preview
    assert all('dt_cutting_tool_13399' in artifact['xml'] for artifact in preview['artifacts'])
    resolved, allowed, issues = resolve_references(draft, ['root'])
    assert not issues
    assert len(allowed) == 3
    fields = resolved.model_dump(by_alias=True)['nodes']
    refs = [fields[fields[f'o{i}']['fields']['ref_dt_cutting_tool']['$node']]['fields'] for i in range(3)]
    uris = [fields[ref['keys'][0]['$node']]['fields']['value'] for ref in refs]
    assert uris[0] == uris[2] and uris[0] != uris[1]
    assert uris[0] == 'https://example.test/global/tools_wp/T1'
    request.draft = draft
    again = compile_tools(request, NC)['draft']
    assert [a['assetNodeId'] for a in again['assets']] == [a.assetNodeId for a in draft.assets]


def test_conflicts_require_resolution_and_sync_current_edited_values():
    request = fixture()
    request.draft.nodes['t2'].fields['effective_cutting_diameter'] = 12
    result = compile_tools(request, NC)
    assert not result['ready'] and 'draft' not in result
    assert result['conflicts'][0]['property'] == 'effective_cutting_diameter'
    request.resolutions = {'T1': {'effective_cutting_diameter': 12}}
    result = compile_tools(request, NC)
    assert result['ready']
    assert tool_values(result['draft']['nodes'], 's0')['effective_cutting_diameter'] == 12
    assert tool_values(result['draft']['nodes'], 's2')['effective_cutting_diameter'] == 12
    request.draft = CreatorDraft.model_validate(result['draft'])
    request.draft.nodes['t0'].fields['effective_cutting_diameter'] = 15
    request.resolutions = {}
    assert not compile_tools(request, NC)['ready']


def test_different_workplan_same_t_gets_separate_asset():
    request = fixture()
    result = compile_tools(request, NC)['draft']
    nodes = result['nodes']
    nodes['wp2'] = {**copy.deepcopy(nodes['wp']), 'nodeId': 'wp2'}
    nodes['wp2']['fields']['its_elements'] = []
    for i in range(3):
        for prefix in ('s', 'o', 't'):
            old, new = f'{prefix}{i}', f'{prefix}b{i}'
            nodes[new] = {**copy.deepcopy(nodes[old]), 'nodeId': new}
        nodes[f'sb{i}']['fields']['its_operation'] = {'$node': f'ob{i}'}
        nodes[f'ob{i}']['fields']['its_tool'] = {'$node': f'tb{i}'}
        nodes['wp2']['fields']['its_elements'].append({'$node': f'sb{i}'})
    result['fileLinks'][0]['workplanNodeId'] = 'wp2'
    request.draft = CreatorDraft.model_validate(result)
    request.workplanNodeId = 'wp2'
    for i, assignment in enumerate(request.assignments):
        assignment.stepNodeId = f'sb{i}'
    compiled = compile_tools(request, NC)['draft']
    assert len({link['assetNodeId'] for link in compiled['toolLinks']}) == 4


def test_inactive_t_ownership_preserved_when_removed_and_restored():
    request = fixture()
    first = compile_tools(request, NC)['draft']
    request.draft = CreatorDraft.model_validate(first)
    changed = NC.replace(b'T2', b'T1')
    analysis = analyze_nc(changed, 'original')
    request.draft.fileLinks[0].sha256 = analysis['sha256']
    request.resolutions = {'T1': {'effective_cutting_diameter': 10}}
    for assignment, event in zip(request.assignments, analysis['events']):
        assignment.eventId = event['eventId']
    result = compile_tools(request, changed)['draft']
    assert next(link for link in result['toolLinks'] if link['toolTag'] == 'T2')['stepNodeIds'] == []
    request.draft = CreatorDraft.model_validate(result)
    request.draft.fileLinks[0].sha256 = analyze_nc(NC, 'original')['sha256']
    for assignment, event in zip(request.assignments, analyze_nc(NC, 'original')['events']):
        assignment.eventId = event['eventId']
    request.resolutions = {'T2': {'effective_cutting_diameter': 6}}
    restored = compile_tools(request, NC)['draft']
    assert len(restored['assets']) == len(first['assets'])


@pytest.mark.parametrize('text, expected', [(b'N10T001M06\nT2\nM6\nM30', ['T1', 'T2']),
    (b'(T9 M6)\nT1 M6 ; T8 M6\nM30', ['T1']), (b'T1\nG0 X0\nM6\nM30', ['T1'])])
def test_legacy_extractor_supports_compact_comments_preselection(text, expected):
    result = analyze_nc(text, 'file')
    assert result['supported'], result
    assert [event['toolTag'] for event in result['events']] == expected


@pytest.mark.parametrize('text', [b'T1 M6\nM6', b'T1 T2 M6', b'T1 M6\nM98 P2', b'T1 M6\n#1=2', b'T1', b'(multiline\nT1 M6', b'T1.5 M6', b'T1 M6 M6'])
def test_ambiguous_nc_is_blocked(text):
    assert not analyze_nc(text, 'file')['supported']


def test_reject_stale_file_order_missing_file_asset_and_unassigned_events():
    request = fixture()
    for modify in [lambda r: setattr(r.draft.fileLinks[0], 'sha256', '0' * 64),
                   lambda r: r.assignments.reverse(), lambda r: r.draft.assets.pop(),
                   lambda r: setattr(r.assignments[1], 'eventId', r.assignments[0].eventId)]:
        altered = request.model_copy(deep=True)
        modify(altered)
        with pytest.raises(CamInputError):
            compile_tools(altered, NC)


def test_many_contiguous_steps_can_share_one_nc_event():
    nc = b'T1 M6\nM30'
    request = fixture(nc)
    event = request.assignments[0].eventId
    request = request.model_copy(update={'assignments': [request.assignments[0].model_copy(update={'stepNodeId': f's{i}', 'eventId': event}) for i in range(3)]})
    request.resolutions = {'T1': {'effective_cutting_diameter': 10}}
    assert len(compile_tools(request, nc)['draft']['toolLinks']) == 1


def test_preview_rejects_stale_values_order_and_missing_link():
    draft = CreatorDraft.model_validate(compile_tools(fixture(), NC)['draft'])
    for modify in [lambda d: d.nodes['t0'].fields.update(effective_cutting_diameter=99),
                   lambda d: d.nodes['wp'].fields['its_elements'].reverse(), lambda d: d.toolLinks.pop()]:
        altered = draft.model_copy(deep=True)
        modify(altered)
        assert resolve_references(altered, ['root'])[2]
    file_preview = preview_assets(draft, ['file'])
    assert not file_preview['valid']
    assert file_preview['pendingStorage'][0]['code'] == 'FILE_STORAGE_PENDING'
    assert any(issue['code'] == 'ASSET_TYPE_MISMATCH' for issue in file_preview['issues'])  # Fixture lacks file schema_version.


def test_nc_apis_are_stateless_and_reject_invalid_multipart(monkeypatch):
    spies = []
    for owner, method in [(AsyncIOMotorCollection, 'insert_one'), (AsyncIOMotorCollection, 'update_one'),
                          (AsyncIOMotorCollection, 'insert_many'), (AsyncIOMotorGridFSBucket, 'upload_from_stream')]:
        spy = AsyncMock(side_effect=AssertionError('Write forbidden'))
        monkeypatch.setattr(owner, method, spy)
        spies.append(spy)
    request = fixture()
    with TestClient(app) as client:
        response = client.post('/api/v3/creator/nc/tools', data={'payload': request.model_dump_json(by_alias=True)}, files={'file:original': ('test.nc', NC)})
        assert response.status_code == 200, response.text
        assert response.json()['ready']
        assert client.post('/api/v3/creator/nc/analyze', data={'payload': '{"fileId":"original"}'}, files={'file:original': ('test.nc', NC)}).json()['supported']
        assert client.post('/api/v3/creator/nc/analyze', data={'payload': '{}'}, files={'file:wrong': ('test.nc', NC)}).status_code == 422
        request.draft.nodes['t0'].fields['its_cutting_edges'] = 1
        response = client.post('/api/v3/creator/nc/tools', data={'payload': request.model_dump_json(by_alias=True)}, files={'file:original': ('test.nc', NC)})
        assert response.status_code == 422, response.text
    for spy in spies:
        spy.assert_not_called()
