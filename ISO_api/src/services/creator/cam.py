"""Bounded, stateless CAM -> editable graph candidates. Never writes assets."""

import copy
import hashlib
import json
import math
import re
from uuid import uuid4

from src.schemas.creator_cam import CamParseRequest
from src.services.creator.catalog import get_catalog
from src.services.creator.cam_mapping import DEFAULT_MAPPINGS
from src.utils.cam_nx_adapter import pick_nx_ops
from src.utils.cam_powermill_adapter import pick_powermill_ops

PARSER_VERSION = "creator-cam-1"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_OPERATIONS = 300
MISSING = object()


class CamInputError(ValueError):
    pass


def load_json(data: bytes):
    if len(data) > MAX_FILE_BYTES:
        raise CamInputError("파일당 8 MiB 제한을 초과했습니다.")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result or key in ("__proto__", "prototype", "constructor"):
                raise CamInputError("중복되거나 안전하지 않은 JSON 키가 있습니다.")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(CamInputError("유한한 숫자만 허용합니다.")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise CamInputError("유효한 UTF-8 JSON 파일이 아닙니다.") from exc
    stack, count = [(value, 0)], 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if depth > 48 or count > 150000:
            raise CamInputError("JSON 깊이 또는 항목 수 제한을 초과했습니다.")
        if isinstance(item, float) and not math.isfinite(item):
            raise CamInputError("유한한 숫자만 허용합니다.")
        if isinstance(item, dict):
            if any(len(key) > 512 for key in item):
                raise CamInputError("JSON 키가 너무 깁니다.")
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
    return value


def compile_mapping(mapping, catalog):
    if not isinstance(mapping, dict) or not 1 <= len(mapping) <= 256:
        raise CamInputError("매핑은 1~256개 항목의 JSON 객체여야 합니다.")
    compiled = []
    types = catalog["types"]
    for source, destination in mapping.items():
        if not isinstance(destination, str) or len(destination) > 2048 or len(source) > 1024:
            raise CamInputError("매핑 경로 형식을 확인해 주세요.")
        parts = destination.split(".")
        if not source or parts[0] != "MachiningWorkingstep":
            raise CamInputError("매핑 대상은 MachiningWorkingstep으로 시작해야 합니다.")
        current, steps, index = parts[0], [], 1
        while index < len(parts):
            name = parts[index]
            field = next((f for f in types[current]["fields"] if f["fieldName"] == name), None)
            if not field or field["managed"]:
                raise CamInputError(f"허용되지 않은 매핑 필드: {current}.{name}")
            index += 1
            if index == len(parts):
                if field["kind"] == "object":
                    raise CamInputError("매핑 마지막 항목은 값 필드여야 합니다.")
                compiled.append((source, steps, field, destination))
                break
            if field["kind"] != "object":
                raise CamInputError("값 필드 아래에 경로가 있습니다.")
            allowed = set(field["objectTypes"])
            allowed.update(child for base in field["objectTypes"] for child in types[base]["descendants"])
            chosen = None
            while index < len(parts) and parts[index] in types:
                candidate = parts[index]
                if candidate not in allowed or (chosen and candidate != chosen and candidate not in types[chosen]["descendants"]):
                    raise CamInputError("매핑 객체의 상속/타입 조합이 올바르지 않습니다.")
                chosen = candidate
                index += 1
            if chosen is None or index == len(parts):
                raise CamInputError("매핑 중간 객체의 타입과 값 필드를 지정해 주세요.")
            steps.append((field, chosen))
            current = chosen
        else:
            raise CamInputError("매핑 값 필드가 없습니다.")
    return compiled


def source_value(operation, path):
    value = operation
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return MISSING
        value = value[key]
    return value


def convert_scalar(raw, field, catalog):
    if field["kind"] == "enum":
        values = catalog["enums"][field["enumTypes"][0]]
        value = next((value for value in values if isinstance(raw, str) and value.lower() == raw.strip().lower()), MISSING)
        if value is MISSING:
            raise CamInputError("허용된 enum 값이 아닙니다. 직접 선택해 주세요.")
        return value
    kinds = field["scalarTypes"]
    if "bool" in kinds:
        if isinstance(raw, bool):
            return raw
        normalized = str(raw).strip().lower()
        if normalized in ("true", "1", "on", "yes"):
            return True
        if normalized in ("false", "0", "off", "no"):
            return False
        raise CamInputError("예/아니오로 확정할 수 없는 원본 값입니다.")
    if "float" in kinds or "int" in kinds:
        if isinstance(raw, bool) or not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", str(raw).strip()):
            raise CamInputError("숫자 형식이나 단위를 확인해 주세요.")
        value = float(raw)
        if not math.isfinite(value) or ("int" in kinds and (not value.is_integer() or abs(value) > 9007199254740991)):
            raise CamInputError("유한한 숫자 또는 안전한 정수 범위를 확인해 주세요.")
        return int(value) if "int" in kinds else value
    if "str" in kinds and isinstance(raw, str):
        return raw
    raise CamInputError("원본과 대상 필드의 값 타입이 다릅니다.")


def new_node(nodes, type_id):
    node = {"nodeId": str(uuid4()), "typeId": type_id, "fields": {}}
    nodes[node["nodeId"]] = node
    return node


def assign(nodes, root_id, steps, field, raw, catalog):
    if field["repeated"]:
        if not isinstance(raw, list):
            raise CamInputError("반복 값은 JSON 배열이어야 합니다.")
        value = [{"itemId": str(uuid4()), "value": convert_scalar(item, field, catalog)} for item in raw]
    else:
        value = convert_scalar(raw, field, catalog)
    node = nodes[root_id]
    for link, chosen in steps:
        ref = node["fields"].get(link["fieldName"])
        if ref is None:
            child = new_node(nodes, chosen)
            ref = {"$node": child["nodeId"]}
            node["fields"][link["fieldName"]] = [ref] if link["repeated"] else ref
        else:
            child = nodes[(ref[0] if link["repeated"] else ref)["$node"]]
            existing = child["typeId"]
            if chosen in catalog["types"][existing]["descendants"]:
                child["typeId"] = chosen
            elif existing != chosen and existing not in catalog["types"][chosen]["descendants"]:
                raise CamInputError("같은 객체에 서로 다른 매핑 타입이 지정되었습니다.")
        node = child
    if field["fieldName"] in node["fields"] and node["fields"][field["fieldName"]] != value:
        raise CamInputError("같은 필드에 서로 다른 원본 값이 매핑되었습니다.")
    node["fields"][field["fieldName"]] = value
    return node["nodeId"], value


def leaf_paths(value, prefix=""):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from leaf_paths(child, f"{prefix}.{key}" if prefix else key)
    else:
        yield prefix


def parse_cam(request: CamParseRequest, files: dict[str, tuple[str, bytes]], mapping_bytes=None):
    catalog = get_catalog()
    if request.schemaHash != catalog["schemaHash"] or request.rulesVersion != catalog["rulesVersion"]:
        raise CamInputError("스키마 버전이 변경되었습니다. 화면을 다시 열어 주세요.")
    if set(files) != set(request.orderedFileIds):
        raise CamInputError("파일 목록과 전송된 파일이 일치하지 않습니다.")
    mapping = load_json(mapping_bytes) if mapping_bytes is not None else DEFAULT_MAPPINGS[request.camType]
    compiled = compile_mapping(mapping, catalog)
    mapping_hash = hashlib.sha256(mapping_bytes if mapping_bytes is not None else json.dumps(mapping, sort_keys=True).encode()).hexdigest()
    results, operations = [], []
    total_nodes = 0
    for file_id in request.orderedFileIds:
        name, data = files[file_id]
        digest = hashlib.sha256(data).hexdigest()
        try:
            content = load_json(data)
            ops = (pick_nx_ops if request.camType == "nx" else pick_powermill_ops)(content)
            if not ops or not all(isinstance(op, dict) and op for op in ops):
                raise CamInputError("가공 작업 객체를 찾을 수 없습니다.")
            if request.camType == "powermill" and len(ops) != 1:
                raise CamInputError("PowerMill은 파일 하나에 작업 하나만 허용합니다.")
            if len(ops) > MAX_OPERATIONS or len(operations) + len(ops) > MAX_OPERATIONS:
                raise CamInputError("한 번에 300개 이하의 작업을 가져올 수 있습니다.")
        except CamInputError as exc:
            results.append({"fileId": file_id, "name": name, "sha256": digest, "operationCount": 0, "error": str(exc)})
            continue
        file_candidates = []
        for index, operation in enumerate(ops):
            nodes = {}
            root = new_node(nodes, "MachiningWorkingstep")
            origins, diagnostics, consumed = [], [], set()
            for source, steps, field, destination in compiled:
                raw = source_value(operation, source)
                if raw is MISSING or raw is None or raw == "":
                    continue
                candidate = copy.deepcopy(nodes)
                try:
                    node_id, value = assign(candidate, root["nodeId"], steps, field, raw, catalog)
                    nodes = candidate
                    consumed.add(source)
                    origins.append({"nodeId": node_id, "fieldName": field["fieldName"], "sourcePath": source, "targetPath": destination, "value": value})
                except CamInputError as exc:
                    diagnostics.append({"code": "VALUE_NOT_MAPPED", "message": str(exc), "sourcePath": source, "nodeId": None, "fieldName": field["fieldName"]})
            if not origins:
                diagnostics.append({"code": "NO_MAPPED_FIELDS", "message": "선택한 형식/매핑에 일치하는 값이 없습니다.", "sourcePath": None, "nodeId": root["nodeId"], "fieldName": None})
            for node in nodes.values():
                for field in catalog["types"][node["typeId"]]["fields"]:
                    if field["required"] and field["fieldName"] not in node["fields"]:
                        diagnostics.append({"code": "REQUIRED_FIELD", "message": f'{catalog["types"][node["typeId"]]["label"]}: {field["label"]} 입력 필요', "sourcePath": None, "nodeId": node["nodeId"], "fieldName": field["fieldName"]})
            paths = [path for path in leaf_paths(operation) if not any(path == used or path.startswith(used + ".") for used in consumed)]
            title = nodes[root["nodeId"]]["fields"].get("its_id") or f"{name} · {index + 1}"
            file_candidates.append({"candidateId": str(uuid4()), "fileId": file_id, "sourceIndex": index,
                "title": title, "rootNodeId": root["nodeId"], "nodes": nodes, "origins": origins,
                "diagnostics": diagnostics, "unmappedPaths": paths[:100], "unmappedCount": len(paths),
                "importable": bool(origins)})
        count = sum(len(candidate["nodes"]) for candidate in file_candidates)
        if total_nodes + count > 10000:
            raise CamInputError("파싱 결과의 객체 수가 제한을 초과했습니다.")
        total_nodes += count
        operations.extend(file_candidates)
        results.append({"fileId": file_id, "name": name, "sha256": digest, "operationCount": len(file_candidates), "error": None})
    return {"requestId": request.requestId, "workplanNodeId": request.workplanNodeId,
        "camType": request.camType, "parserVersion": PARSER_VERSION, "mappingHash": mapping_hash,
        "mapping": mapping, "fileResults": results, "operations": operations,
        "partial": any(item["error"] for item in results), "persisted": False}
