from unittest.mock import AsyncMock
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket

from src.creator_app import app
from src.services.creator.preview import preview_assets
from src.services.creator.references import resolve_references
from test_nc import fixture


def draft_file():
    draft = fixture().draft
    draft.nodes['file'].fields.update(schema_version='v31', asset_global_id='https://example.test/file')
    return draft


@pytest.mark.parametrize('purpose', ['NC', 'STEP', 'OTHER'])
def test_local_file_can_preview_metadata_without_persisted_value(purpose):
    draft = draft_file()
    draft.fileLinks[0].purpose = purpose
    if purpose != 'NC':
        draft.fileLinks[0].workplanNodeId = None
    before = draft.model_dump(by_alias=True)
    result = preview_assets(draft, ['file'])
    assert result['valid'], result
    assert result['issues'] == [] and not result['finalizable'] and not result['machineReady']
    assert result['validationScope'] == 'partial-file-metadata'
    assert result['pendingStorage'][0]['code'] == 'FILE_STORAGE_PENDING'
    artifact = result['artifacts'][0]
    assert artifact['reviewOnly']
    assert artifact['omittedFields'] == [{'nodeId': 'file-element', 'fieldName': 'value'}]
    xml = ET.fromstring(artifact['xml'])
    file = xml.find('.//{*}dt_elements')
    assert file is not None
    assert file.find('{*}value') is None  # Reference KeyValue.value elements must still exist.
    assert file.find('{*}path').text == 'test.nc'
    assert file.find('{*}content_type').text == 'text/x-gcode'
    keys = {key.find('{*}key').text: key.find('{*}value').text for key in file.findall('.//{*}keys')}
    assert keys['DT_PROJECT'] == 'project' and keys['DT_ASSET'] == 'job'
    assert ('WORKPLAN' in keys) == (purpose == 'NC')
    assert draft.model_dump(by_alias=True) == before
    assert resolve_references(draft, ['file'])[2]  # Strict resolution still refuses an unstored file.


@pytest.mark.parametrize('field', ['path', 'content_type', 'element_id'])
def test_real_required_file_fields_still_block_xml(field):
    draft = draft_file()
    del draft.nodes['file-element'].fields[field]
    result = preview_assets(draft, ['file'])
    assert not result['valid'] and result['artifacts'] == []
    assert any(issue['fieldName'] == field and issue['code'] == 'REQUIRED_FIELD' for issue in result['issues'])
    assert result['pendingStorage']


def test_unregistered_file_does_not_gain_required_value_exemption():
    draft = draft_file()
    draft.fileLinks = []
    result = preview_assets(draft, ['file'])
    assert not result['valid']
    assert any(issue['fieldName'] == 'value' for issue in result['issues'])
    assert not result['pendingStorage']


@pytest.mark.parametrize('value', ['fake-id', '', 0, False])
def test_user_cannot_fabricate_a_stored_file_id(value):
    draft = draft_file()
    draft.nodes['file-element'].fields['value'] = value
    result = preview_assets(draft, ['file'])
    assert not result['valid'] and not result['artifacts']
    assert '저장 ID를 직접 지정' in result['issues'][0]['message']


def test_missing_nc_workplan_is_not_downgraded_to_pending_storage():
    draft = draft_file()
    draft.fileLinks[0].workplanNodeId = None
    result = preview_assets(draft, ['file'])
    assert not result['valid'] and not result['artifacts']
    assert '워크플랜을 배정' in result['issues'][0]['message']


def test_file_preview_endpoint_never_persists(monkeypatch):
    spies = []
    for owner, method in [(AsyncIOMotorCollection, 'insert_one'), (AsyncIOMotorCollection, 'update_one'),
                          (AsyncIOMotorCollection, 'insert_many'), (AsyncIOMotorCollection, 'replace_one'),
                          (AsyncIOMotorGridFSBucket, 'upload_from_stream')]:
        spy = AsyncMock(side_effect=AssertionError('Write forbidden'))
        monkeypatch.setattr(owner, method, spy)
        spies.append(spy)
    with TestClient(app) as client:
        result = client.post('/api/v3/creator/review', json={'draft': draft_file().model_dump(by_alias=True), 'targetAssetNodeIds': ['file'], 'mode': 'partial'})
        assert result.status_code == 200, result.text
        assert result.json()['artifacts'] and result.json()['pendingStorage']
    for spy in spies:
        spy.assert_not_called()
