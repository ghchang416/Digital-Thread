from unittest.mock import AsyncMock
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket

from src.creator_app import app
from src.schemas.creator import CreatorDraft
from src.services.creator.catalog import get_catalog
from src.services.creator.preview import preview_assets


@pytest.fixture
def payload():
    catalog = get_catalog()
    return {
        "draftVersion": 1, "schemaVersion": "v31", "schemaHash": catalog["schemaHash"],
        "rulesVersion": catalog["rulesVersion"], "draftId": "draft", "revision": 0,
        "projectAssetNodeId": "root", "assets": [{"assetNodeId": "root", "elementNodeId": "material", "role": "material"}],
        "nodes": {
            "root": {"nodeId": "root", "typeId": "DtAsset", "fields": {"asset_global_id": "https://digital-thread.re/test", "id": "material_asset", "schema_version": "v31", "dt_elements": [{"$node": "material"}]}},
            "material": {"nodeId": "material", "typeId": "DtMaterial", "fields": {"element_id": "steel", "standard_identifier": "ISO", "material_identifier": "Steel"}},
        },
    }


def preview(payload):
    return preview_assets(CreatorDraft.model_validate(payload), ["root"])


def test_catalog_complete():
    catalog = get_catalog()
    assert len(catalog["types"]) == 600
    assert len(catalog["enums"]) == 35
    assert catalog["capabilities"]["finalSave"] is False
    for name, info in catalog["types"].items():
        assert name not in info["descendants"]
        for field in info["fields"]:
            assert all(ref in catalog["types"] for ref in field["objectTypes"])
            assert all(ref in catalog["enums"] for ref in field["enumTypes"])
    fields = {field["fieldName"]: field for field in catalog["types"]["MachineToolRequirements"]["fields"]}
    assert fields["automatically_pallet_changeable"]["required"] is True
    assert fields["spindles"]["repeated"] is True


def test_material_xml(payload):
    result = preview(payload)
    assert result["valid"] and not result["finalizable"]
    assert 'xsi:type="dt_material"' in result["artifacts"][0]["xml"]


@pytest.mark.parametrize("type_id,fields", [
    ("NumericParameter", {"parameter_name": "density", "its_parameter_value": 0, "its_parameter_unit": "kg/m3"}),
    ("DescriptiveParameter", {"parameter_name": "condition", "descriptive_string": "A&B <steel>"}),
])
def test_property_subtypes(payload, type_id, fields):
    payload["nodes"]["prop"] = {"nodeId": "prop", "typeId": type_id, "fields": fields}
    payload["nodes"]["material"]["fields"]["material_property"] = [{"$node": "prop"}]
    result = preview(payload)
    assert result["valid"], result
    xml = result["artifacts"][0]["xml"]
    if type_id == "NumericParameter":
        value = ElementTree.fromstring(xml).find(".//{*}its_parameter_value")
        assert value is not None and float(value.text) == 0
    else:
        assert "A&amp;B &lt;steel&gt;" in xml


def test_missing_property_field(payload):
    payload["nodes"]["prop"] = {"nodeId": "prop", "typeId": "NumericParameter", "fields": {"parameter_name": "density"}}
    payload["nodes"]["material"]["fields"]["material_property"] = [{"$node": "prop"}]
    result = preview(payload)
    assert not result["valid"]
    assert {i["fieldName"] for i in result["issues"]} == {"its_parameter_value", "its_parameter_unit"}


def test_optional_absent_has_no_child_errors(payload):
    assert preview(payload)["issues"] == []


@pytest.mark.parametrize("key,value,code", [
    ("element_id", " ", "REQUIRED_FIELD"),
    ("standard_identifier", 12, "INVALID_SCALAR"),
    ("material_property", "bad", "CARDINALITY"),
    ("invented", "bad", "UNKNOWN_FIELD"),
])
def test_bad_fields(payload, key, value, code):
    payload["nodes"]["material"]["fields"][key] = value
    assert code in {i["code"] for i in preview(payload)["issues"]}


def test_enum_rejected(payload):
    payload["nodes"]["root"]["fields"]["asset_kind"] = "unknown"
    assert preview(payload)["issues"][0]["code"] == "INVALID_ENUM"


def test_wrong_child(payload):
    payload["nodes"]["material"]["fields"]["material_property"] = [{"$node": "root"}]
    assert preview(payload)["issues"][0]["code"] == "INVALID_OBJECT_TYPE"


def test_cycle(payload):
    payload["assets"][0]["role"] = "project"
    payload["nodes"]["material"] = {"nodeId": "material", "typeId": "DtProject", "fields": {"element_id": "p", "its_id": "p", "main_workplan": {"$node": "wp"}}}
    payload["nodes"]["wp"] = {"nodeId": "wp", "typeId": "Workplan", "fields": {"its_id": "wp", "its_elements": [{"$node": "wp"}]}}
    assert "CYCLIC_GRAPH" in {i["code"] for i in preview(payload)["issues"]}


def test_false_preserved(payload):
    payload["assets"][0]["role"] = "machine"
    payload["nodes"]["material"] = {"nodeId": "material", "typeId": "DtMachineTool", "fields": {"element_id": "machine", "machine_tool": {"$node": "req"}}}
    payload["nodes"]["req"] = {"nodeId": "req", "typeId": "MachineToolRequirements", "fields": {"description": "Machine", "automatically_pallet_changeable": False}}
    result = preview(payload)
    assert result["valid"], result
    assert ">false<" in result["artifacts"][0]["xml"]


def test_version_mismatch(payload):
    payload["schemaHash"] = "0" * 64
    assert preview(payload)["issues"][0]["code"] == "SCHEMA_VERSION_MISMATCH"


def test_api_no_writes(payload, monkeypatch):
    spies = []
    for owner, name in [(AsyncIOMotorCollection, "insert_one"), (AsyncIOMotorCollection, "update_one"), (AsyncIOMotorCollection, "insert_many"), (AsyncIOMotorCollection, "replace_one"), (AsyncIOMotorGridFSBucket, "upload_from_stream")]:
        spy = AsyncMock(side_effect=AssertionError("Write forbidden"))
        monkeypatch.setattr(owner, name, spy)
        spies.append(spy)
    with TestClient(app) as client:
        response = client.get("/api/v3/creator/schema")
        assert response.status_code == 200
        assert client.get("/api/v3/creator/schema", headers={"If-None-Match": response.headers["etag"]}).status_code == 304
        result = client.post("/api/v3/creator/review", json={"mode": "partial", "draft": payload, "targetAssetNodeIds": ["root"]})
        assert result.status_code == 200 and result.json()["valid"]
        assert client.post("/api/v3/creator/submissions", json={}).status_code == 404
    for spy in spies:
        spy.assert_not_called()


def test_body_limit():
    with TestClient(app) as client:
        assert client.post("/api/v3/creator/review", content=b"x" * (2 * 1024 * 1024 + 1)).status_code == 413


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(unknown=True),
    lambda p: p["nodes"]["material"].update(nodeId="other"),
    lambda p: p["nodes"]["material"]["fields"].update(standard_identifier=None),
    lambda p: p["nodes"]["material"]["fields"].update(standard_identifier={"__class__": "bad"}),
])
def test_strict_dto(payload, mutate):
    mutate(payload)
    with TestClient(app) as client:
        assert client.post("/api/v3/creator/review", json={"mode": "partial", "draft": payload, "targetAssetNodeIds": ["root"]}).status_code == 422
