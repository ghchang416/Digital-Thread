import copy
from unittest.mock import AsyncMock
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket

from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.services.creator.catalog import get_catalog
from src.services.creator.preview import preview_assets
from src.services.creator.schema_provider import get_model, get_profile, validate_profile


def reference_draft():
    catalog = get_catalog()
    nodes, assets = {}, []

    def node(node_id, type, **fields):
        nodes[node_id] = {"nodeId": node_id, "typeId": type, "fields": fields}
        return {"$node": node_id}

    def asset(id, role, type, **fields):
        element = node(id + "-element", type, element_id=id + "-element", **fields)
        node(id, "DtAsset", asset_global_id="https://example.test/kitech", id=id,
             schema_version="v31", dt_elements=[element])
        assets.append({"assetNodeId": id, "elementNodeId": id + "-element", "role": role})

    piece = node("piece", "Workpiece", its_id="part")
    child = node("child", "Workplan", its_id="child")
    wp = node("wp", "Workplan", its_id="main", its_elements=[child])
    asset("root", "project", "DtProject", its_id="project", main_workplan=wp, its_workpieces=[piece])
    for id in ("steel", "aluminium"):
        asset(id, "material", "DtMaterial", standard_identifier="ISO", material_identifier=id)
    for id in ("mill", "lathe"):
        asset(id, "machine", "DtMachineTool", machine_tool=node(id + "-req", "MachineToolRequirements", description=id, automatically_pallet_changeable=False))
    return {"schemaHash": catalog["schemaHash"], "rulesVersion": catalog["rulesVersion"], "draftId": "refs", "revision": 0,
            "projectAssetNodeId": "root", "nodes": nodes, "assets": assets, "referencePolicyHash": catalog["referencePolicyHash"],
            "referenceLinks": [
                {"sourceNodeId": "piece", "policyId": "workpiece-material", "targetAssetNodeId": "steel"},
                {"sourceNodeId": "wp", "policyId": "workplan-machine", "targetAssetNodeId": "mill"},
                {"sourceNodeId": "child", "policyId": "workplan-machine", "targetAssetNodeId": "lathe"},
            ]}


def review(payload, target="root"):
    return preview_assets(CreatorDraft.model_validate(payload), [target])


def test_reference_create_update_remove_and_current_ids():
    payload = reference_draft()
    original = copy.deepcopy(payload)
    result = review(payload)
    assert result["valid"], result
    assert not result["finalizable"]
    tree = ET.fromstring(result["artifacts"][0]["xml"])
    assert [e.text for e in tree.findall(".//{*}ref_dt_material/{*}keys/{*}value")] == ["https://example.test/kitech/steel/steel-element"]
    assert set(e.text for e in tree.findall(".//{*}ref_dt_machine_tool/{*}keys/{*}value")) == {"https://example.test/kitech/mill/mill-element", "https://example.test/kitech/lathe/lathe-element"}
    assert payload == original
    payload["referenceLinks"][0]["targetAssetNodeId"] = "aluminium"
    payload["nodes"]["aluminium"]["fields"]["id"] = "renamed"
    assert "https://example.test/kitech/renamed/aluminium-element" in review(payload)["artifacts"][0]["xml"]
    payload["referenceLinks"] = []
    assert "ref_dt_" not in review(payload)["artifacts"][0]["xml"]


@pytest.mark.parametrize("mutate,code", [
    (lambda p: p.update(referencePolicyHash="0" * 64), "REFERENCE_POLICY_MISMATCH"),
    (lambda p: p.pop("referencePolicyHash"), "REFERENCE_POLICY_MISMATCH"),
    (lambda p: p["referenceLinks"][0].update(targetAssetNodeId="missing"), "DT_LINK_INVALID"),
    (lambda p: p["referenceLinks"][0].update(targetAssetNodeId="mill"), "DT_LINK_INVALID"),
    (lambda p: p["referenceLinks"][0].update(policyId="unknown"), "DT_LINK_INVALID"),
    (lambda p: p["referenceLinks"][0].update(sourceNodeId="wp"), "DT_LINK_INVALID"),
    (lambda p: p["referenceLinks"][0].update(policyId="operation-tool"), "DT_LINK_INVALID"),
    (lambda p: p["referenceLinks"].append(p["referenceLinks"][0].copy()), "DT_LINK_INVALID"),
    (lambda p: p["nodes"]["piece"]["fields"].update(ref_dt_material={"$node": "wp"}), "DT_LINK_INVALID"),
    (lambda p: p["nodes"]["steel"]["fields"].update(id=""), "DT_LINK_INVALID"),
    (lambda p: p["nodes"]["steel"]["fields"].update(asset_global_id="http://[invalid"), "DT_LINK_INVALID"),
    (lambda p: p["nodes"]["steel"]["fields"].update(schema_version="other"), "DT_LINK_INVALID"),
    (lambda p: p["nodes"]["steel"]["fields"].update(dt_elements=[]), "DT_LINK_INVALID"),
    (lambda p: p["nodes"]["root-element"]["fields"].pop("its_workpieces"), "DT_LINK_INVALID"),
])
def test_invalid_reference_is_not_silently_dropped(mutate, code):
    payload = reference_draft()
    mutate(payload)
    result = review(payload)
    assert not result["valid"] and not result["artifacts"]
    assert code in {i["code"] for i in result["issues"]}


def test_duplicate_identity_and_missing_source():
    payload = reference_draft()
    payload["nodes"]["aluminium"]["fields"]["id"] = "steel"
    payload["nodes"]["aluminium-element"]["fields"]["element_id"] = "steel-element"
    assert not review(payload)["valid"]
    payload = reference_draft()
    del payload["nodes"]["piece"]
    assert not review(payload)["valid"]


def test_inline_material_is_preserved_and_manual_reference_is_rejected():
    payload = reference_draft()
    payload["nodes"]["inline"] = {"nodeId": "inline", "typeId": "Material", "fields": {"standard_identifier": "ISO", "material_identifier": "inline"}}
    payload["nodes"]["piece"]["fields"]["its_material"] = {"$node": "inline"}
    result = review(payload)
    assert result["valid"], result
    assert "<its_material>" in result["artifacts"][0]["xml"]
    payload["referenceLinks"] = []
    payload["nodes"]["piece"]["fields"]["ref_dt_material"] = {"$node": "wp"}
    assert "MANAGED_REFERENCE" in {i["code"] for i in review(payload)["issues"]}


def test_legacy_drafts_and_independent_asset_review():
    payload = reference_draft()
    assert review(payload, "steel")["valid"]
    payload.pop("referenceLinks")
    payload.pop("referencePolicyHash")
    assert review(payload)["valid"]


def test_profile_validates_schema_and_catalog_marks_inherited_fields():
    catalog = get_catalog()
    assert next(f for f in catalog["types"]["MachiningOperation"]["fields"] if f["fieldName"] == "ref_dt_cutting_tool")["referencePolicyId"] == "operation-tool"
    profile = get_profile().model_copy(deep=True)
    profile.referencePolicies[0] = profile.referencePolicies[0].model_copy(update={"fieldName": "missing"})
    with pytest.raises(ValueError):
        validate_profile(profile, get_model())
    profile = get_profile().model_copy(deep=True)
    profile.referencePolicies.append(profile.referencePolicies[0])
    with pytest.raises(ValueError):
        validate_profile(profile, get_model())


def test_review_api_no_storage_writes(monkeypatch):
    spies = []
    for owner, name in [(AsyncIOMotorCollection, "insert_one"), (AsyncIOMotorCollection, "update_one"), (AsyncIOMotorGridFSBucket, "upload_from_stream")]:
        spy = AsyncMock(side_effect=AssertionError("No persistence during review"))
        monkeypatch.setattr(owner, name, spy)
        spies.append(spy)
    with TestClient(app) as client:
        response = client.post("/api/v3/creator/review", json={"draft": reference_draft(), "targetAssetNodeIds": ["root"]})
        assert response.status_code == 200 and response.json()["valid"]
        schema = client.get("/api/v3/creator/schema")
        assert get_catalog()["referencePolicyHash"] in schema.headers["etag"]
    for spy in spies:
        spy.assert_not_called()
