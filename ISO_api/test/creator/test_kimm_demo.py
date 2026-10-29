"""Read-only acceptance using the operator's actual KIMM CAM/NC inputs."""
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket
from xsdata.formats.dataclass.parsers import XmlParser

from src.creator_app import app
from src.services.creator.catalog import get_catalog
from src.services.creator.nc import to_graph
from src.services.creator.schema_provider import get_model


ORDER = ['face1', '2D_contour3', '2D_contour4', 'drill4', '2D_pocket2', '2D_pocket4', '2D_pocket7', '2D_pocket6']


def demo_flow(client, directory):
    catalog = client.get('/api/v3/creator/schema').json()
    cam_dir = next(p for p in directory.iterdir() if p.is_dir() and p.name.startswith('1'))
    nc = (cam_dir / 'merge.tap').read_bytes()
    ids = [f'cam{i}' for i in range(8)]
    payload = dict(requestId='kimm-demo', schemaHash=catalog['schemaHash'], rulesVersion=catalog['rulesVersion'],
                   workplanNodeId='wp', camType='powermill', orderedFileIds=ids)
    files = {f'file:{id}': (name + '.json', (cam_dir / 'Json' / (name + '.json')).read_bytes()) for id, name in zip(ids, ORDER)}
    parsed = client.post('/api/v3/creator/cam/parse', data={'payload': json.dumps(payload)}, files=files)
    assert parsed.status_code == 200, parsed.text
    candidates = parsed.json()['operations']
    assert len(candidates) == 8 and all(c['importable'] for c in candidates)
    nodes = {}
    def node(node_id, type, **fields):
        nodes[node_id] = dict(nodeId=node_id, typeId=type, fields=fields)
        return {'$node': node_id}
    for candidate in candidates:
        nodes.update(candidate['nodes'])
    steps = [c['rootNodeId'] for c in candidates]
    project = node('project', 'DtProject', element_id='project', its_id='kimm_demo', display_name='기계연 시연',
        main_workplan=node('main', 'Workplan', its_id='메인 워크플랜', its_elements=[node('wp', 'Workplan', its_id='1차 가공', its_elements=[{'$node': id} for id in steps])]))
    global_id = 'https://digital-thread.re/kitech/kimm_demo'
    node('root', 'DtAsset', asset_global_id=global_id, id='project', schema_version='v31', asset_kind='instance', dt_elements=[project])
    node('file', 'DtAsset', asset_global_id=global_id, id='nc', schema_version='v31', asset_kind='instance', dt_elements=[node('file-element', 'DtFile', element_id='nc', category='NC', content_type='text/x-gcode', path='merge.tap')])
    assets = [dict(assetNodeId='root', elementNodeId='project', role='project'), dict(assetNodeId='file', elementNodeId='file-element', role='file')]
    for role, filename in [('machine', '기계연_machine_tool.xml'), ('material', '기계연_material.xml')]:
        root = to_graph(XmlParser().from_string((directory / filename).read_text(encoding='utf-8'), get_model().DtAsset), nodes)['$node']
        element = nodes[root]['fields']['dt_elements'][0]['$node']
        assets.append(dict(assetNodeId=root, elementNodeId=element, role=role))
    analysis_response = client.post('/api/v3/creator/nc/analyze', data={'payload': json.dumps(dict(fileId='nc-source', encoding='cp949'))}, files={'file:nc-source': ('merge.tap', nc)})
    assert analysis_response.status_code == 200, analysis_response.text
    analysis = analysis_response.json()
    assert analysis['supported'], analysis
    assert [e['toolTag'] for e in analysis['events']] == ['T1', 'T2', 'T2', 'T3', 'T4', 'T4', 'T4', 'T4']
    draft = dict(draftVersion=1, schemaVersion='v31', schemaHash=catalog['schemaHash'], rulesVersion=catalog['rulesVersion'],
        draftId='kimm-demo', revision=1, nodes=nodes, assets=assets, projectAssetNodeId='root',
        fileLinks=[dict(assetNodeId='file', fileId='nc-source', sha256=analysis['sha256'], purpose='NC', workplanNodeId='wp')])
    completed = client.post('/api/v3/creator/workplans/complete', json=dict(draft=draft, workplanNodeId='wp', includePlaceholders=True, mode='missing-only', overrides={}))
    assert completed.status_code == 200, completed.text
    draft = completed.json()['draft']
    draft['referencePolicyHash'] = catalog['referencePolicyHash']
    material_id = next(a['assetNodeId'] for a in assets if a['role'] == 'material')
    draft['referenceLinks'] = [dict(sourceNodeId='wp', policyId='workplan-machine', targetAssetNodeId=next(a['assetNodeId'] for a in assets if a['role'] == 'machine'))]
    for id, value in draft['nodes'].items():
        if value['typeId'] == 'Workpiece':
            draft['referenceLinks'].append(dict(sourceNodeId=id, policyId='workpiece-material', targetAssetNodeId=material_id))
    compiled = client.post('/api/v3/creator/nc/tools', data={'payload': json.dumps(dict(draft=draft, workplanNodeId='wp', fileId='nc-source', fileAssetNodeId='file', encoding='cp949',
        assignments=[dict(stepNodeId=id, eventId=event['eventId']) for id, event in zip(steps, analysis['events'])], resolutions={}))}, files={'file:nc-source': ('merge.tap', nc)})
    assert compiled.status_code == 200, compiled.text
    assert compiled.json()['ready'], compiled.json()
    draft = compiled.json()['draft']
    assert len([a for a in draft['assets'] if a['role'] == 'tool']) == 4
    outputs = []
    for asset in draft['assets']:
        response = client.post('/api/v3/creator/review', json=dict(mode='partial', draft=draft, targetAssetNodeIds=[asset['assetNodeId']]))
        assert response.status_code == 200, response.text
        review = response.json()
        assert review['valid'], (asset['role'], review['issues'])
        assert len(review['artifacts']) == 1
        XmlParser().from_string(review['artifacts'][0]['xml'], get_model().DtAsset)
        outputs.append(review)
    assert len(outputs) == 8
    assert any(result.get('pendingStorage') for result in outputs)
    assert any(result.get('warnings') for result in outputs)
    assert all(not result['finalizable'] for result in outputs)
    return draft, outputs


def test_actual_kimm_cam_nc_xml_without_database_writes(monkeypatch):
    directory = Path(os.environ.get('KIMM_DATA_DIR', '/data/xml/기계연'))
    if not directory.exists():
        pytest.skip('KIMM_DATA_DIR not available; actual acceptance must be run separately')
    spies = []
    for owner, methods in [(AsyncIOMotorCollection, ['insert_one', 'insert_many', 'update_one', 'update_many', 'replace_one', 'delete_one', 'delete_many', 'bulk_write']),
                           (AsyncIOMotorGridFSBucket, ['upload_from_stream', 'delete'])]:
        for method in methods:
            spy = AsyncMock(side_effect=AssertionError('Database writes forbidden'))
            monkeypatch.setattr(owner, method, spy); spies.append(spy)
    with TestClient(app) as client:
        draft, outputs = demo_flow(client, directory)
    for spy in spies:
        spy.assert_not_called()
    print(f'KIMM: 8 CAM, 8 NC events, 4 tools, {len(outputs)} XML, no database writes')
