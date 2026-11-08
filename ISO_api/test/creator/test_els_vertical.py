"""Representative staged ELS milling flow. No production database or workspace writes."""
from copy import deepcopy

from fastapi.testclient import TestClient
import pytest
from xsdata.formats.dataclass.parsers import XmlParser

from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.schemas.creator_els import ElsBuildRequest, ElsCandidate, ElsConfirmRequest
from src.services.creator.els.build import prepare
from src.services.creator.els.profile import load_profile
from src.services.creator.els.reader import AccessTable
from src.services.creator.els.review import confirm, review, snapshot_hash
from src.services.creator.els.selection import source_context
from src.services.creator.els.source_catalog import SourceCatalog
from src.services.creator.manual import prepare_tool, manual_profile
from src.schemas.creator_manual import ManualToolRequest
from src.services.creator.schema_provider import get_model
from test_els_source_catalog import snapshot
from test_els_reader import runtime, fixture_path
from test_nc import fixture


def context_and_request(*, placeholders=True, mode="replace-project"):
    source = snapshot()
    for op in source.tables["operation_info"].rows:
        op.update({"공정 Type": "MILLING", "설비코드": "MC", "설비번호": "001"})
    for part in source.tables["part_info"].rows:
        part.update(Part_Material="AL6061")
    for row in source.tables["operation_machining"].rows:
        row.update(DIAMETER_SETPOINT=10, SPINDLE_01=6000, FEED_01=600)
    for name, rows in [("Machine_Milling", [{"설비코드": "MC", "설비번호": "001", "설비명": "Synthetic machine"}]),
                       ("Part_File", [{"Part_No": "P1", "Part_Rev": "01", "File_Path": "//offline/share/program.nc"}])]:
        source.tables[name.lower()] = AccessTable(name, [], [], rows)
    for table in source.tables.values():
        table.columns = [dict(name=k, type="TEXT", readable=True) for k in table.rows[0]]
    catalog = SourceCatalog(source)
    op = next(o for o in catalog.operations if o["opNo"] == "010" and o["partRevision"] == "01")
    program = catalog.details[op["operationKey"]]["programs"][0]
    context = source_context(catalog, op["operationKey"], program["programKey"])
    context["sourceName"] = "synthetic.mdb"
    base = fixture().draft
    request = ElsBuildRequest(request=dict(requestId="request", importId="import", baseDraftId=base.draftId,
        baseRevision=base.revision, expectedSequence=3, mode=mode, profileHash=load_profile()[1], includePlaceholders=placeholders,
        selection=dict(partNo="P1", partRevision="01", opNo="010", programNo="100", programRevision="A",
            orderedRowIds=[r["rowId"] for r in context["rows"]])),
        baseDraft=base, operationKey=op["operationKey"], programKey=program["programKey"],
        projectName="ELS milling", globalAssetBaseUri="https://example.test/els/",
        decisions=dict(millingConfirmed=True, templateReason="Operator selected the representative authoring template",
            valueChoices=[dict(rowId=r["rowId"], ruleId="diameter", column="DIAMETER_SETPOINT", reason="Effective diameter confirmed") for r in context["rows"]],
            fileChoices=[] if mode == "append-tools" else [dict(rowId=context["files"][0]["rowId"], purpose="NC", reason="Selected program metadata")]))
    return context, request


def build():
    context, request = context_and_request()
    return prepare(context, request)


def confirmed(candidate=None):
    candidate = candidate or build()
    return confirm(ElsConfirmRequest(candidate=candidate, acknowledged=True,
                   workplanNodeIds=[w.workplanNodeId for w in candidate.metadata.elsWorkplans]))


def test_vertical_prepare_confirm_xml_roundtrip_and_originals_preserved():
    context, request = context_and_request()
    original = deepcopy((context, request))
    candidate = prepare(context, request)
    assert (context, request) == original
    assert candidate.draft.draftId != request.baseDraft.draftId and candidate.draft.revision == 0
    assert not candidate.draft.manualWorkplans and not candidate.draft.manualToolLinks
    assert not candidate.draft.ncReviews and not candidate.draft.toolLinks and not candidate.draft.fileLinks
    assert len([a for a in candidate.draft.assets if a.role == "tool"]) == 1
    assert len([n for n in candidate.draft.nodes.values() if n.typeId == "Workpiece"]) == 1
    assert not review(candidate, [candidate.draft.projectAssetNodeId])["valid"]
    for asset in candidate.draft.assets:
        prepared = review(candidate, [asset.assetNodeId], require_confirmation=False)
        assert prepared["valid"], (asset.role, prepared)
    checked = confirmed(candidate)
    assert not candidate.metadata.elsReviews and checked.metadata.elsReviews
    all_xml = []
    for asset in checked.draft.assets:
        result = review(checked, [asset.assetNodeId])
        assert result["valid"], result
        assert not result["finalizable"] and not result["machineReady"] and not result["persisted"]
        xml = result["artifacts"][0]["xml"]
        XmlParser().from_string(xml, get_model().DtAsset)
        all_xml.append(xml)
        if asset.role == "project":
            assert "ref_dt_cutting_tool" in xml and "ref_dt_material" in xml and "ref_dt_machine_tool" in xml
        if asset.role == "file":
            assert result["artifacts"][0]["omittedFields"] == [dict(nodeId=asset.elementNodeId, fieldName="value")]
            assert result["pendingStorage"][0]["sourceFileAvailable"] is False
        if asset.role == "tool":
            assert any(w["code"] == "ELS_PLACEHOLDER" for w in result["warnings"])
    assert len(all_xml) == 5
    technologies = [n for n in checked.draft.nodes.values() if n.typeId == "MillingTechnology"]
    assert all(n.fields["spindle"] == 100 and n.fields["feedrate"] == .01 for n in technologies)


@pytest.mark.parametrize("change", ["source-scope", "revision", "profile", "turning", "exclude", "sequence", "diameter", "tool-conflict", "machine", "invalid-number"])
def test_source_ambiguity_never_hidden_by_placeholders(change):
    context, request = context_and_request()
    if change == "source-scope": request.request.selection.opNo = "10"
    if change == "revision": request.request.baseRevision += 1
    if change == "profile": request.request.profileHash = "0" * 64
    if change == "turning": context["operation"]["values"]["공정 Type"] = "TURNING"
    if change == "exclude": request.request.selection.orderedRowIds.pop()
    if change == "sequence": request.request.selection.orderedRowIds.reverse()
    if change == "diameter": request.decisions.valueChoices = []
    if change == "tool-conflict": context["rows"][0]["values"]["DIAMETER_SETPOINT"] = 12
    if change == "machine": context["machines"] *= 2
    if change == "invalid-number": context["rows"][0]["values"]["SPINDLE_01"] = -1000
    with pytest.raises(ValueError, match="ELS_"):
        prepare(context, request)


def test_explicit_order_and_source_choice_preserve_unrepresented_values():
    context, request = context_and_request()
    context["rows"][0]["values"].update(SPINDLE_01=0, SPINDLE_02=5000, FEED_01=0)
    from src.schemas.creator_els import ElsValueChoice
    request.decisions.valueChoices.append(ElsValueChoice(rowId=context["rows"][0]["rowId"], ruleId="spindle", column="SPINDLE_01", reason="Zero selected; other condition remains unrepresented"))
    request.request.selection.orderedRowIds.reverse()
    request.request.selection.orderReason = "Operator reviewed the corrected order"
    candidate = prepare(context, request)
    assert candidate.metadata.elsImports[0].sourceRows[0].values["SPINDLE_02"] == 5000
    assert any(n.fields.get("spindle") == 0 and n.fields.get("feedrate") == 0 for n in candidate.draft.nodes.values() if n.typeId == "MillingTechnology")
    assert [s.sourceRowId for s in candidate.metadata.elsWorkplans[0].steps] == request.request.selection.orderedRowIds


def test_missing_tool_identity_needs_explicit_non_dummy_confirmation():
    context, request = context_and_request()
    for row in context["rows"]: del row["values"]["DIAMETER_SETPOINT"]
    request.decisions.valueChoices = []
    with pytest.raises(ValueError, match="IDENTITY_REQUIRED"):
        prepare(context, request)
    from src.schemas.creator_els import ElsIdentityChoice
    request.decisions.identityChoices = [ElsIdentityChoice(rowId=r["rowId"], configurationId="assembly-confirmed", reason="Operator checked identical assembly") for r in context["rows"]]
    candidate = prepare(context, request)
    assert len([a for a in candidate.draft.assets if a.role == "tool"]) == 1
    request.decisions.identityChoices[1].configurationId = "different-assembly"
    with pytest.raises(ValueError, match="CONFIGURATION_CONFLICT"):
        prepare(context, request)


@pytest.mark.parametrize("mutation", ["speed", "order", "source", "raw-ref", "tool", "removed-dimension", "workpiece", "file-value", "profile", "type", "request-profile", "request-selection"])
def test_modified_or_forged_candidate_requires_reconfirmation_or_resolution(mutation):
    candidate = confirmed()
    wp = candidate.metadata.elsWorkplans[0]
    step = candidate.draft.nodes[wp.steps[0].stepNodeId]
    op = candidate.draft.nodes[step.fields["its_operation"].node]
    if mutation == "speed": candidate.draft.nodes[op.fields["its_technology"].node].fields["spindle"] = 200
    if mutation == "order": candidate.draft.nodes[wp.workplanNodeId].fields["its_elements"].reverse()
    if mutation == "source": candidate.metadata.elsImports[0].sourceRows[0].values["SPINDLE_01"] = 2000
    if mutation == "raw-ref": op.fields["ref_dt_cutting_tool"] = step.fields["its_operation"]
    if mutation == "tool": candidate.draft.nodes[op.fields["its_tool"].node].fields["overall_assembly_length"] = 50
    if mutation == "removed-dimension":
        asset = next(a for a in candidate.draft.assets if a.role == "tool")
        candidate.draft.nodes[asset.elementNodeId].fields["numerical_value"].pop()
    if mutation == "workpiece": candidate.draft.nodes[step.fields["its_feature"].node].fields["its_workpiece"] = step.fields["its_operation"]
    if mutation == "file-value":
        asset = next(a for a in candidate.draft.assets if a.role == "file")
        candidate.draft.nodes[asset.elementNodeId].fields["value"] = "fake-gridfs-id"
    if mutation == "profile": candidate.metadata.elsImports[0].profileHash = "0" * 64
    if mutation == "type": op.typeId = "PlaneRoughMilling"
    if mutation == "request-profile": candidate.request.profileHash = "0" * 64
    if mutation == "request-selection": candidate.request.selection.orderReason = "Changed request without evidence"
    result = review(candidate, [candidate.draft.projectAssetNodeId])
    assert not result["valid"] and not result["artifacts"], result


def test_unused_tool_does_not_invalidate_confirmation_but_used_tool_does():
    candidate = confirmed()
    wp = candidate.metadata.elsWorkplans[0].workplanNodeId
    before = snapshot_hash(candidate, wp)
    result = prepare_tool(ManualToolRequest(draft=candidate.draft, expectedRevision=0, profileHash=manual_profile()["hash"],
        name="UNUSED", toolTypeId="MillingCuttingTool", values={}))
    result["draft"]["revision"] = 0
    candidate.draft = CreatorDraft.model_validate(result["draft"])
    assert snapshot_hash(candidate, wp) == before
    assert review(candidate, [candidate.draft.projectAssetNodeId])["valid"]


def test_append_tools_keeps_all_existing_data_and_ignores_existing_nc_incompleteness():
    context, request = context_and_request(mode="append-tools")
    original = request.baseDraft.model_dump(by_alias=True)
    candidate = prepare(context, request)
    updated = candidate.draft.model_dump(by_alias=True)
    assert candidate.draft.revision == request.baseDraft.revision + 1
    for name in original.keys() - {"revision", "nodes", "assets", "manualTools"}:
        assert original[name] == updated[name]
    assert all(updated["nodes"][k] == v for k, v in original["nodes"].items())
    new_asset = candidate.draft.assets[-1]
    assert review(candidate, [new_asset.assetNodeId])["valid"]
    assert not candidate.metadata.elsWorkplans and not candidate.metadata.elsReviews
    legacy = review(candidate, [candidate.draft.projectAssetNodeId])
    assert not legacy["valid"] and not legacy["artifacts"]


def test_metadata_file_exception_never_applies_to_unlinked_file():
    candidate = confirmed()
    file = next(a for a in candidate.draft.assets if a.role == "file")
    candidate.metadata.elsFileLinks = []
    result = review(candidate, [file.assetNodeId])
    assert not result["valid"] and not result["artifacts"]


@pytest.mark.parametrize("name", ["synthetic.mdb", "synthetic.accdb"])
def test_actual_access_through_session_selection_to_xml(runtime, tmp_path, name):
    import hashlib
    from src.services.creator.els.sessions import ImportSessions
    from src.schemas.creator_els import ElsIdentityChoice, ElsValueChoice, ElsFileChoice, ElsSelection
    path = fixture_path(name)
    original = hashlib.sha256(path.read_bytes()).hexdigest()
    sessions = ImportSessions(tmp_path / "sessions", reader=runtime)
    try:
        import_id, token = sessions.reserve("vertical-test")
        sessions.append(import_id, token, path.read_bytes())
        sessions.submit(import_id, token, name)
        sessions._sessions[import_id].future.result(timeout=10)
        assert sessions.status(import_id, token)["status"] == "ready", sessions.status(import_id, token)
        catalog = sessions._sessions[import_id].catalog
        op = next(o for o in catalog.operations if o["partRevision"] == "01" and o["opNo"] == "010")
        program = next(p for p in catalog.details[op["operationKey"]]["programs"] if p["pgmNo"] == "100")
        context = sessions.source_context(import_id, token, op["operationKey"], program["programKey"])
        _, request = context_and_request()
        request.operationKey, request.programKey = op["operationKey"], program["programKey"]
        request.request.importId = import_id
        request.request.selection = ElsSelection(partNo=op["partNo"], partRevision=op["partRevision"], opNo=op["opNo"],
            programNo=context["programNo"], programRevision=context["programRevision"], orderedRowIds=[r["rowId"] for r in context["rows"]])
        request.decisions.identityChoices = [ElsIdentityChoice(rowId=r["rowId"], configurationId="operator-checked-T1",
            reason="Same physical assembly confirmed; no source dimensions") for r in context["rows"]]
        request.decisions.valueChoices = [ElsValueChoice(rowId=r["rowId"], ruleId="spindle", column="SPINDLE_01",
            reason="Representative condition selected, second condition retained") for r in context["rows"]]
        request.decisions.fileChoices = [ElsFileChoice(rowId=context["files"][0]["rowId"], purpose="NC", reason="Path metadata only")]
        candidate = prepare(context, request)
        sessions.delete(import_id, token)
        checked = confirmed(candidate)
        for asset in checked.draft.assets:
            result = review(checked, [asset.assetNodeId])
            assert result["valid"], result
            XmlParser().from_string(result["artifacts"][0]["xml"], get_model().DtAsset)
        assert any(n.fields.get("spindle") == 0 for n in checked.draft.nodes.values() if n.typeId == "MillingTechnology")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == original
    finally:
        sessions.close()


def test_without_placeholders_returns_incomplete_candidate_and_cannot_confirm():
    context, request = context_and_request(placeholders=False)
    candidate = prepare(context, request)
    assert not any(o.kind == "placeholder" for o in candidate.metadata.elsOrigins)
    assert not review(candidate, [candidate.draft.projectAssetNodeId], require_confirmation=False)["valid"]
    with pytest.raises(ValueError, match="CONFIRM_VALIDATION_FAILED"):
        confirmed(candidate)


def test_confirm_and_review_http_work_without_reader_or_import_session(monkeypatch):
    monkeypatch.delenv("CREATOR_ELS_ENABLED", raising=False)
    candidate = build()
    client = TestClient(app)
    response = client.post("/api/v3/creator/els/confirm", json=dict(candidate=candidate.model_dump(by_alias=True),
        acknowledged=True, workplanNodeIds=[w.workplanNodeId for w in candidate.metadata.elsWorkplans]))
    assert response.status_code == 200, response.text
    checked = response.json()
    result = client.post("/api/v3/creator/els/review", json=dict(candidate=checked, targetAssetNodeIds=[candidate.draft.projectAssetNodeId]))
    assert result.status_code == 200 and result.json()["valid"], result.text
    assert client.post("/api/v3/creator/review", json=dict(candidate=checked)).status_code == 422


def test_missing_only_completion_is_idempotent_and_keeps_real_workpiece():
    from src.schemas.creator_els import ElsCompleteRequest
    from src.services.creator.els.complete import complete
    context, request = context_and_request(placeholders=False)
    candidate = prepare(context, request)
    before = candidate.model_dump(by_alias=True)
    wp = candidate.metadata.elsWorkplans[0].workplanNodeId
    result = complete(ElsCompleteRequest(candidate=candidate, workplanNodeId=wp, includePlaceholders=True))
    assert candidate.model_dump(by_alias=True) == before
    assert len([n for n in result.draft.nodes.values() if n.typeId == "Workpiece"]) == 1
    for n in result.draft.nodes.values():
        if n.typeId == "MillingTechnology": assert n.fields["spindle"] == 100
    checked = confirmed(result)
    again = complete(ElsCompleteRequest(candidate=checked, workplanNodeId=wp, includePlaceholders=True))
    assert again == checked
    assert review(again, [again.draft.projectAssetNodeId])["valid"]


def test_completion_requires_opt_in_to_overwrite_tool_and_invalidates_confirmation():
    from src.schemas.creator_els import ElsCompleteRequest
    from src.services.creator.els.complete import complete
    candidate = confirmed()
    wp = candidate.metadata.elsWorkplans[0]
    step = candidate.draft.nodes[wp.steps[0].stepNodeId]
    op = candidate.draft.nodes[step.fields["its_operation"].node]
    candidate.draft.nodes[op.fields["its_tool"].node].fields["overall_assembly_length"] = 99
    before = deepcopy(candidate)
    with pytest.raises(ValueError):
        complete(ElsCompleteRequest(candidate=candidate, workplanNodeId=wp.workplanNodeId, includePlaceholders=True))
    assert candidate == before
    result = complete(ElsCompleteRequest(candidate=candidate, workplanNodeId=wp.workplanNodeId, includePlaceholders=True, synchronizeTools=True))
    assert not result.metadata.elsReviews
    assert review(confirmed(result), [result.draft.projectAssetNodeId])["valid"]


def test_stage_api_with_owned_session_does_not_modify_base_or_require_database(tmp_path):
    from src.apis.v3.creator_els import get_sessions
    from src.services.creator.els.sessions import ImportSessions
    from test_els_sessions import ACCESS, FakeReader
    source = snapshot()
    for op in source.tables["operation_info"].rows:
        op.update({"공정 Type": "MILLING"})
    class Reader(FakeReader):
        def read(self, stream, *, cancelled): return deepcopy(source)
    sessions = ImportSessions(tmp_path, reader=Reader())
    app.dependency_overrides[get_sessions] = lambda: sessions
    try:
        client = TestClient(app)
        created = client.post("/api/v3/creator/els/imports", headers={"X-ELS-Request-Id": "vertical"}, files={"file": ("source.mdb", ACCESS)})
        assert created.status_code == 202, created.text
        import_id, token = created.json()["importId"], created.json()["ownerToken"]
        sessions._sessions[import_id].future.result(timeout=5)
        context, request = context_and_request()
        op = next(o for o in sessions.operations(import_id, token)["items"] if o["opNo"] == "010" and o["partRevision"] == "01")
        pgm = sessions.operation(import_id, token, op["operationKey"])["programs"]["items"][0]
        url = f"/api/v3/creator/els/imports/{import_id}"
        headers = {"X-ELS-Owner-Token": token}
        response = client.get(url + f"/operations/{op['operationKey']}/programs/{pgm['programKey']}/source", headers=headers)
        assert response.status_code == 200, response.text
        source_context = response.json()
        request.request.importId = import_id
        request.operationKey, request.programKey = op["operationKey"], pgm["programKey"]
        request.request.selection.orderedRowIds = [r["rowId"] for r in source_context["rows"]]
        request.includeMachine = False
        request.decisions.valueChoices, request.decisions.fileChoices = [], []
        from src.schemas.creator_els import ElsIdentityChoice
        request.decisions.identityChoices = [ElsIdentityChoice(rowId=r, configurationId="same-assembly", reason="Operator confirmed same assembly") for r in request.request.selection.orderedRowIds]
        before = request.baseDraft.model_dump(by_alias=True)
        assert client.post(url + "/prepare", json=request.model_dump(by_alias=True)).status_code == 404
        result = client.post(url + "/prepare", headers=headers, json=request.model_dump(by_alias=True))
        assert result.status_code == 200 and result.json()["ready"], result.text
        candidate = ElsCandidate.model_validate(result.json()["candidate"])
        assert request.baseDraft.model_dump(by_alias=True) == before
        assert client.delete(url, headers=headers).status_code == 204
        assert review(confirmed(candidate), [candidate.draft.projectAssetNodeId])["valid"]
    finally:
        app.dependency_overrides.pop(get_sessions, None)
        sessions.close()
