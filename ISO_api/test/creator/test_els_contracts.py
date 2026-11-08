import copy
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.schemas.creator_els import ElsCandidate, ElsImport, ElsMetadata, ElsSourceRow
from src.services.creator.catalog import get_catalog
from src.services.creator.els.contracts import check_request_budget, validate_candidate_metadata, validate_application
from src.services.creator.els.profile import load_profile, numeric_candidate
from src.services.creator.els.tool_identity import group_source_tools
from src.services.creator.els import capabilities as capability_module
from src.services.creator.manual import manual_profile
from src.services.creator.preview import preview_assets
from test_nc import fixture
from test_manual import tool, completed


def source_import():
    return dict(importEntryId='import1', sourceSha256='a' * 64, sourceName='synthetic.accdb',
                readerVersion='jackcess-4.0.8/els-1', sourceSchemaHash='b' * 64, profileHash=load_profile()[1],
                selection=dict(partNo='P001', partRevision='01', opNo='010', programNo='100', programRevision='A',
                               orderedRowIds=['r0', 'r1', 'r2']),
                sourceRows=[dict(rowId=f'r{i}', table='Operation_Machining', values={
                    'Part_No': 'P001', 'Part_Rev': '01', 'Op_No': '010', 'PGMNO': '100', 'REVNO': 'A',
                    'TOOLNO': '001', 'SEQNO': i * 10, 'SPINDLE_01': 0, 'SPINDLE_02': None}) for i in range(3)])


def candidate_parts():
    result = tool(fixture().draft.model_dump(by_alias=True))
    draft = CreatorDraft.model_validate(result['draft'])
    metadata = ElsMetadata(elsImports=[source_import()], elsWorkplans=[dict(workplanNodeId='wp', importEntryId='import1',
        steps=[dict(kind='els', stepNodeId=f's{i}', sourceRowId=f'r{i}') for i in range(3)])],
        elsToolLinks=[dict(workplanNodeId='wp', stepNodeId=f's{i}', assetNodeId=result['assetNodeId'], toolTag='T1', sourceToolNo='001') for i in range(3)])
    return draft, metadata


def test_profile_is_separate_and_validates_all_targets_against_current_model():
    before_catalog, before_manual = copy.deepcopy(get_catalog()), copy.deepcopy(manual_profile())
    profile, profile_hash = load_profile()
    assert len(profile_hash) == 64 and profile.status == 'staged-vertical'
    assert all(c.status in {'verified-staged-vertical', 'deferred'} for c in profile.coverage)
    assert get_catalog() == before_catalog and manual_profile() == before_manual
    assert not any(r.targetField in {'overall_assembly_length', 'maximum_depth_of_cut'} for r in profile.numericRules)
    assert 'STICKOUT' in profile.preserveOnlyColumns and 'AXIAL_DEPTH_MAX' in profile.preserveOnlyColumns


@pytest.mark.parametrize('rule_id,row,status,expected', [
    ('spindle', {'SPINDLE_01': 6000}, 'candidate', '100'),
    ('spindle', {'SPINDLE_01': 6000, 'SPINDLE_02': 6000}, 'candidate', '100'),
    ('spindle', {'SPINDLE_01': 3000, 'SPINDLE_02': 6000}, 'selection-required', None),
    ('spindle', {'SPINDLE_01': 0, 'SPINDLE_02': None}, 'candidate', '0'),
    ('spindle', {'SPINDLE_01': -1000}, 'invalid', None),
    ('spindle', {'SPINDLE_01': False}, 'invalid', None),
    ('spindle', {'SPINDLE_01': 'NaN'}, 'invalid', None),
    ('feedrate', {'FEED_04': Decimal('600')}, 'candidate', '0.01'),
    ('feedrate', {'FEED_01': '', 'FEED_02': None}, 'missing', None),
    ('diameter', {'DIAMETER_SETPOINT': 10}, 'selection-required', None),
])
def test_numeric_candidates_preserve_zero_units_and_conflicts(rule_id, row, status, expected):
    rule = next(r for r in load_profile()[0].numericRules if r.id == rule_id)
    original = copy.deepcopy(row)
    result = numeric_candidate(rule, row)
    assert result['status'] == status and result.get('value') == expected
    assert row == original


def test_explicit_numeric_choice_retains_unrepresented_and_invalid_columns():
    rule = load_profile()[0].numericRules[0]
    row = {'SPINDLE_01': 3000, 'SPINDLE_02': -1000}
    with pytest.raises(ValueError):
        numeric_candidate(rule, row, column='SPINDLE_01')
    selected = numeric_candidate(rule, row, column='SPINDLE_01', reason='Representative speed confirmed')
    assert selected['value'] == '50' and selected['unrepresentedColumns'] == ['SPINDLE_02']


@pytest.mark.parametrize('mutation', ['number-key', 'wrong-op', 'wrong-revision', 'duplicate-row', 'excluded-selected', 'extra-field'])
def test_import_contract_rejects_ambiguous_or_cross_program_selection(mutation):
    value = source_import()
    if mutation == 'number-key': value['selection']['opNo'] = 10
    if mutation == 'wrong-op': value['sourceRows'][0]['values']['Op_No'] = '10'
    if mutation == 'wrong-revision': value['sourceRows'][0]['values']['REVNO'] = 'B'
    if mutation == 'duplicate-row': value['sourceRows'].append(value['sourceRows'][0])
    if mutation == 'excluded-selected': value['selection']['excludedRows'] = [{'rowId': 'r0', 'reason': 'exclude'}]
    if mutation == 'extra-field': value['latestRevision'] = True
    with pytest.raises(ValidationError): ElsImport.model_validate(value)


def test_valid_preflight_is_non_mutating_and_not_a_confirmation():
    draft, metadata = candidate_parts()
    original = copy.deepcopy((draft, metadata))
    result = validate_candidate_metadata(draft, metadata)
    assert result['confirmationRequired'] and result['persisted'] is False
    assert (draft, metadata) == original
    assert metadata.elsReviews == [] and draft.ncReviews == []


@pytest.mark.parametrize('mutation,code', [
    ('manual-mode', 'MODE_CONFLICT'), ('legacy-tool', 'MODE_CONFLICT'), ('nc-review', 'MODE_CONFLICT'),
    ('missing-tool', 'MISSING_TOOL_LINK'), ('order', 'ORDER_MISMATCH'), ('profile', 'PROFILE_MISMATCH'),
    ('second-parent', 'STEP_OWNERSHIP'), ('detached-wp', 'NOT_IN_PROJECT'),
    ('cycle', 'CYCLIC_GRAPH'), ('file-blob', 'FILE_MODE_CONFLICT'), ('file-value', 'FILE_MODE_CONFLICT'),
    ('source-tag', 'TOOL_SOURCE_MISMATCH'), ('raw-reference', 'RAW_MANAGED_REFERENCE'),
])
def test_ownership_and_file_modes_fail_closed(mutation, code):
    draft, metadata = candidate_parts()
    d, m = draft.model_dump(by_alias=True), metadata.model_dump(by_alias=True)
    if mutation == 'manual-mode': d['manualWorkplans'] = ['wp']
    if mutation == 'legacy-tool': d['toolLinks'] = [{'workplanNodeId': 'wp', 'toolTag': 'T1', 'assetNodeId': m['elsToolLinks'][0]['assetNodeId'], 'stepNodeIds': ['s0']}]
    if mutation == 'nc-review': d['ncReviews'] = [{'workplanNodeId': 'wp', 'fileId': 'original', 'sha256': 'a' * 64, 'stepNodeIds': ['s0']}]
    if mutation == 'missing-tool': m['elsToolLinks'].pop()
    if mutation == 'order': d['nodes']['wp']['fields']['its_elements'].reverse()
    if mutation == 'profile': m['elsImports'][0]['profileHash'] = '0' * 64
    if mutation == 'second-parent': d['nodes']['another'] = {'nodeId': 'another', 'typeId': 'Workplan', 'fields': {'its_elements': [{'$node': 's0'}]}}
    if mutation == 'detached-wp': del d['nodes']['project']['fields']['main_workplan']
    if mutation == 'cycle': d['nodes']['s0']['fields']['its_feature'] = {'$node': 's0'}
    if mutation == 'source-tag': m['elsToolLinks'][0]['sourceToolNo'] = '002'
    if mutation == 'raw-reference': d['nodes']['o0']['fields']['ref_dt_cutting_tool'] = {'$node': 't0'}
    if mutation.startswith('file-'):
        m['elsImports'][0]['sourceRows'].append({'rowId': 'f0', 'table': 'Part_File', 'values': {'File_Path': 'test.nc'}})
        m['elsFileLinks'] = [{'assetNodeId': 'file', 'projectAssetNodeId': 'root', 'workplanNodeId': 'wp', 'importEntryId': 'import1', 'sourceRowId': 'f0', 'sourcePath': 'test.nc', 'purpose': 'NC'}]
        if mutation == 'file-value':
            d['fileLinks'] = []
            d['nodes']['file-element']['fields']['value'] = 'fake-id'
    before = copy.deepcopy((d, m))
    with pytest.raises(ValueError, match=code):
        validate_candidate_metadata(CreatorDraft.model_validate(d), ElsMetadata.model_validate(m))
    assert (d, m) == before


def test_request_budget_is_utf8_and_checks_the_complete_envelope():
    check_request_budget({'payload': 'a' * 1000})
    with pytest.raises(ValueError, match='REQUEST_BUDGET'):
        check_request_budget({'payload': '가' * 700000})
    draft, metadata = candidate_parts()
    d = draft.model_dump(by_alias=True)
    d['nodes']['project']['fields']['its_id'] = 'a' * 1835008
    with pytest.raises(ValueError, match='DRAFT_BUDGET'):
        validate_candidate_metadata(CreatorDraft.model_validate(d), metadata)


def test_replace_and_append_identity_contracts_are_distinct():
    draft, metadata = candidate_parts()
    request = dict(requestId='request', importId='temporary', baseDraftId=draft.draftId, baseRevision=draft.revision,
                   expectedSequence=3, mode='append-tools', profileHash=load_profile()[1], selection=source_import()['selection'])
    with pytest.raises(ValidationError): ElsCandidate(request=request, draft=draft, metadata=metadata)
    next_draft = draft.model_copy(update={'revision': draft.revision + 1})
    assert ElsCandidate(request=request, draft=next_draft, metadata=metadata).recoveryFormatVersion == 2
    request['mode'] = 'replace-project'
    with pytest.raises(ValidationError): ElsCandidate(request=request, draft=next_draft, metadata=metadata)
    replacement = draft.model_copy(update={'draftId': 'replacement', 'revision': 0})
    assert ElsCandidate(request=request, draft=replacement, metadata=metadata).persisted is False
    with pytest.raises(ValidationError): ElsCandidate(request=request, draft=replacement, metadata=metadata, machineReady=True)


def test_els_metadata_is_not_yet_accepted_by_active_draft_api():
    draft, metadata = candidate_parts()
    with pytest.raises(ValidationError):
        CreatorDraft.model_validate({**draft.model_dump(by_alias=True), **metadata.model_dump(by_alias=True)})


def test_capability_stays_off_even_with_flag_and_reader(monkeypatch):
    monkeypatch.setenv('CREATOR_ELS_ENABLED', '1')
    monkeypatch.setattr(capability_module.AccessReader, 'available', lambda _: True)
    before = copy.deepcopy(get_catalog())
    result = TestClient(app).get('/api/v3/creator/els/capabilities')
    assert result.status_code == 200
    body = result.json()
    assert body['readerPresent'] and body['requested'] and body['enabled'] is False
    assert body['reasons'] == ['IMPLEMENTATION_PENDING']
    assert get_catalog() == before


def test_missing_or_invalid_profile_does_not_break_legacy_schema(monkeypatch):
    def invalid(): raise ValueError('bad profile')
    monkeypatch.setattr(capability_module, 'load_profile', invalid)
    client = TestClient(app)
    assert 'PROFILE_INVALID' in client.get('/api/v3/creator/els/capabilities').json()['reasons']
    assert client.get('/api/v3/creator/schema').status_code == 200


def test_unrelated_new_tool_preserves_existing_server_nc_confirmation():
    draft, _, _ = completed()
    previous_reviews = copy.deepcopy(draft['ncReviews'])
    updated = tool(draft, name='UNUSED')['draft']
    assert updated['ncReviews'] == previous_reviews
    assert preview_assets(CreatorDraft.model_validate(updated), ['root'])['valid']


def test_source_tool_identity_uses_configuration_not_row_sn_or_placeholder_values():
    original = source_import()['sourceRows']
    for i, row in enumerate(original):
        row['values'].update(DIAMETER_SETPOINT=10, HOLDER_01='H1', Operation_Machining_SN=i, SPINDLE_01=1000 * i)
    original[1]['values']['TOOLNO'] = 'T1'
    rows = [ElsSourceRow(**r) for r in original]
    before = copy.deepcopy(rows)
    groups = group_source_tools(rows)
    assert len(groups) == 1 and groups[0]['rowIds'] == ['r0', 'r1', 'r2']
    assert rows == before
    rows[1].values['HOLDER_01'] = 'H2'
    with pytest.raises(ValueError, match='CONFIGURATION_CONFLICT'): group_source_tools(rows)
    with pytest.raises(ValueError, match='IDENTITY_REQUIRED'):
        group_source_tools([ElsSourceRow(**r) for r in source_import()['sourceRows']])


def test_tool_identity_never_merges_different_program_scopes_or_guesses_t_number():
    rows = [ElsSourceRow(**r) for r in source_import()['sourceRows']]
    for row in rows: row.values['DIAMETER_SETPOINT'] = 10
    rows[1].values['PGMNO'] = '200'
    with pytest.raises(ValueError, match='SCOPE_MISMATCH'): group_source_tools(rows)
    rows[1].values['PGMNO'] = '100'
    rows[0].values['TOOLNO'] = 'unknown'
    with pytest.raises(ValueError, match='TAG_REQUIRED'): group_source_tools(rows)


def test_graph_depth_and_expansion_are_bounded_before_application():
    draft, metadata = candidate_parts()
    value = draft.model_dump(by_alias=True)
    value['nodes']['s0']['fields']['its_feature'] = {'$node': 'deep0'}
    for i in range(65):
        value['nodes'][f'deep{i}'] = {'nodeId': f'deep{i}', 'typeId': 'ToolpathFeature', 'fields': {'its_workpiece': {'$node': f'deep{i + 1}'}} if i < 64 else {}}
    with pytest.raises(ValueError, match='DEPTH_LIMIT'):
        validate_candidate_metadata(CreatorDraft.model_validate(value), metadata)
    value = draft.model_dump(by_alias=True)
    value['nodes']['s0']['fields']['its_feature'] = {'$node': 'wide0'}
    for i in range(15):
        value['nodes'][f'wide{i}'] = {'nodeId': f'wide{i}', 'typeId': 'Workplan', 'fields': {'its_elements': [{'$node': f'wide{i+1}'}, {'$node': f'wide{i+1}'}]} if i < 14 else {}}
    with pytest.raises(ValueError, match='EXPANSION_LIMIT'):
        validate_candidate_metadata(CreatorDraft.model_validate(value), metadata)


def test_import_dto_keeps_null_empty_zero_and_false_distinct():
    value = source_import()
    value['sourceRows'][0]['values'].update(TEST_EMPTY='', TEST_NULL=None, TEST_ZERO=0, TEST_FALSE=False, TEST_DECIMAL='123456789012345678.123456')
    restored = ElsImport.model_validate_json(ElsImport(**value).model_dump_json()).sourceRows[0].values
    assert restored['TEST_EMPTY'] == '' and restored['TEST_NULL'] is None
    assert type(restored['TEST_ZERO']) is int and type(restored['TEST_FALSE']) is bool
    assert restored['TEST_DECIMAL'] == '123456789012345678.123456'


def test_large_source_numbers_and_empty_tool_selection_fail_closed():
    with pytest.raises(ValidationError):
        ElsSourceRow(rowId='large', table='Part_Info', values={'SN': 9007199254740993})
    assert ElsSourceRow(rowId='large', table='Part_Info', values={'SN': '9007199254740993'}).values['SN'] == '9007199254740993'
    rule = load_profile()[0].numericRules[0]
    assert numeric_candidate(rule, {'SPINDLE_01': '1e99999'})['status'] == 'invalid'
    with pytest.raises(ValueError, match='SELECTION_LIMIT'): group_source_tools([])


def append_candidate():
    draft, _, _ = completed()
    base = CreatorDraft.model_validate(draft)
    updated = CreatorDraft.model_validate(tool(draft, name='APPEND')['draft'])
    request = dict(requestId='request', importId='session', baseDraftId=base.draftId, baseRevision=base.revision,
                   expectedSequence=1, mode='append-tools', profileHash=load_profile()[1], selection=source_import()['selection'])
    return base, ElsCandidate(request=request, draft=updated, metadata=ElsMetadata(elsImports=[source_import()]))


def test_append_application_preserves_confirmed_nc_files_graph_and_baseline():
    base, candidate = append_candidate()
    original = copy.deepcopy((base, candidate))
    assert validate_application(candidate, base)['confirmationRequired']
    assert (base, candidate) == original
    assert candidate.draft.ncReviews == base.ncReviews
    assert candidate.draft.fileLinks == base.fileLinks


@pytest.mark.parametrize('mutation,code', [('node', 'EXISTING_NODE'), ('file', 'EXISTING_DATA'),
    ('review', 'EXISTING_DATA'), ('source', 'EXISTING_SOURCE'), ('orphan', 'GRAPH_OWNERSHIP'), ('stale', 'STALE_BASE')])
def test_append_rejects_changes_to_existing_workspace_contract(mutation, code):
    base, candidate = append_candidate()
    value = candidate.model_dump(by_alias=True)
    if mutation == 'node': value['draft']['nodes']['project']['fields']['its_id'] = 'changed'
    if mutation == 'file': value['draft']['fileLinks'] = []
    if mutation == 'review': value['draft']['ncReviews'] = []
    if mutation == 'source': value['metadata']['elsOrigins'] = [dict(importEntryId='import1', nodeId='project', fieldName='its_id', kind='manual', appliedValue='changed', rule='manual', reason='changed')]
    if mutation == 'orphan': value['draft']['nodes']['orphan'] = dict(nodeId='orphan', typeId='Workplan', fields={})
    if mutation == 'stale': base = base.model_copy(update={'revision': base.revision + 1})
    with pytest.raises(ValueError, match=code): validate_application(ElsCandidate(**value), base)
