import json
import copy
import io
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket

from src.creator_app import app
from src.schemas.creator_cam import CamParseRequest
from src.services.creator.cam import CamInputError, compile_mapping, load_json, parse_cam
from src.services.creator.catalog import get_catalog
from src.utils.cam_nx_adapter import pick_nx_ops
from src.utils.cam_powermill_adapter import pick_powermill_ops, reorder_powermill_files_by_order
from starlette.datastructures import UploadFile


def request(cam_type="powermill", ids=None):
    catalog = get_catalog()
    return CamParseRequest(requestId="request", schemaHash=catalog["schemaHash"], rulesVersion=catalog["rulesVersion"],
                           workplanNodeId="wp", camType=cam_type, orderedFileIds=ids or ["one"])


def power(name="Rough", coolant="off"):
    return {"macroRead": {"TOOLPATHNAME": name, "STRATEGY": "offset_area_clear", "MCONDITION1_FEEDRATE": "1200",
                          "MCONDITION1_SPINDLE": "0", "MCONDITION1_COOLANT": coolant, "CUTDIRECTION1_CUTDIR": "climb"},
            "ClsTool": {"ToolType": "end_mill", "ToolD": 10, "ToolR": 0, "NumberOfFlutes": 2}}


def encoded(value):
    return json.dumps(value).encode()


def test_power_mapping_preserves_zero_false_and_provenance():
    result = parse_cam(request(), {"one": ("one.json", encoded(power()))})
    candidate = result["operations"][0]
    fields = [node["fields"] for node in candidate["nodes"].values()]
    assert any(item.get("spindle") == 0 for item in fields)
    assert any(item.get("coolant") is False for item in fields)
    assert candidate["origins"] and candidate["importable"]
    assert result["persisted"] is False
    assert "its_secplane" not in candidate["nodes"][candidate["rootNodeId"]]["fields"]
    assert any(item["code"] == "REQUIRED_FIELD" for item in candidate["diagnostics"])


def test_ambiguous_boolean_and_enum_are_not_defaulted():
    source = power(coolant="mist")
    source["macroRead"]["CUTDIRECTION1_CUTDIR"] = "unknown"
    result = parse_cam(request(), {"one": ("one.json", encoded(source))})["operations"][0]
    assert len([item for item in result["diagnostics"] if item["code"] == "VALUE_NOT_MAPPED"]) == 2
    assert all("coolant" not in node["fields"] and "cutmode" not in node["fields"] for node in result["nodes"].values())


def test_power_order_uses_ids_not_names_and_one_operation_per_file():
    result = parse_cam(request(ids=["two", "one", "bad"]), {
        "one": ("same.json", encoded(power("First"))), "two": ("same.json", encoded(power("Second"))),
        "bad": ("bad.json", encoded([power(), power()])),
    })
    assert [op["title"] for op in result["operations"]] == ["Second", "First"]
    assert result["partial"] and result["fileResults"][-1]["error"]


def test_nx_multiple_operations():
    source = {"values": [{"Object Information": {"Object name": "A"}, "Tool Information": {"(D) Diameter": "12"}},
                         {"Object Information": {"Object name": "B"}, "Feed Rate": {"Cut": "500"}}]}
    result = parse_cam(request("nx"), {"one": ("nx.json", encoded(source))})
    assert [op["title"] for op in result["operations"]] == ["A", "B"]


@pytest.mark.parametrize("data", [b"{", b'{"a":NaN}', b'{"a":1,"a":2}', b'{"__proto__":{}}', b'{"a":1e9999}'])
def test_invalid_json(data):
    with pytest.raises(CamInputError):
        load_json(data)


@pytest.mark.parametrize("path", ["os.system", "MachiningWorkingstep.unknown", "MachiningWorkingstep.its_operation.DtMaterial.element_id"])
def test_mapping_allowlist(path):
    with pytest.raises(CamInputError):
        compile_mapping({"value": path}, get_catalog())


def test_custom_mapping_and_unmapped_values():
    result = parse_cam(request(), {"one": ("source.json", encoded({"name": "Custom", "unmapped": 1}))},
                       encoded({"name": "MachiningWorkingstep.its_id"}))
    assert result["operations"][0]["title"] == "Custom"
    assert result["operations"][0]["unmappedPaths"] == ["unmapped"]


def test_request_rejects_multi_nx_and_duplicate_ids():
    with pytest.raises(ValueError):
        request("nx", ["one", "two"])
    with pytest.raises(ValueError):
        request(ids=["one", "one"])


def test_no_known_values_not_importable():
    assert not parse_cam(request(), {"one": ("wrong.json", b'{"unknown":1}')})["operations"][0]["importable"]


def test_api_no_writes_and_closes_files(monkeypatch):
    spies = []
    for owner, method in [(AsyncIOMotorCollection, "insert_one"), (AsyncIOMotorCollection, "update_one"),
                          (AsyncIOMotorCollection, "insert_many"), (AsyncIOMotorGridFSBucket, "upload_from_stream")]:
        spy = AsyncMock(side_effect=AssertionError("Write forbidden"))
        monkeypatch.setattr(owner, method, spy)
        spies.append(spy)
    with TestClient(app) as client:
        response = client.post("/api/v3/creator/cam/parse", data={"payload": request().model_dump_json()},
                               files={"file:one": ("source.json", encoded(power()), "application/json")})
        assert response.status_code == 200, response.text
        assert response.json()["operations"][0]["title"] == "Rough"
        assert client.post("/api/v3/creator/cam/parse", data={"payload": request().model_dump_json()},
                           files={"file:wrong": ("source.json", encoded(power()))}).status_code == 422
    for spy in spies:
        spy.assert_not_called()


def test_legacy_adapters_and_ordering_keep_their_existing_contract():
    operations = [power("A"), power("B")]
    for key in ("values", "operations", "ops", "toolpaths", "steps", "items"):
        source = {key: operations}
        before = copy.deepcopy(source)
        assert pick_nx_ops(source) == operations
        assert source == before
    for key in ("operation", "toolpath", "items"):
        assert pick_powermill_ops({key: operations}) == operations
        assert pick_powermill_ops({key: operations[0]}) == operations[:1]
    files = [UploadFile(io.BytesIO(b"{}"), filename="First.json"), UploadFile(io.BytesIO(b"{}"), filename="Second.json")]
    assert reorder_powermill_files_by_order(files, "second,FIRST.json") == files[::-1]
    assert len(pick_powermill_ops(operations)) == 2  # Single-op restriction belongs only to creator.


def test_creator_file_limits_and_bom_json():
    with TestClient(app) as client:
        response = client.post("/api/v3/creator/cam/parse", data={"payload": request().model_dump_json()},
                               files={"file:one": ("large.json", b" " * (8 * 1024 * 1024 + 1), "application/json")})
        assert response.status_code == 413
    result = parse_cam(request(), {"one": ("bom.json", b"\xef\xbb\xbf" + encoded(power()))})
    assert result["operations"][0]["title"] == "Rough"
