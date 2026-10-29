"""Manual authoring, with no CAM dependency or persistence side effects."""
import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

from src.schemas.creator import CreatorDraft
from src.services.creator.cam import CamInputError
from src.services.creator.catalog import get_catalog
from src.services.creator.nc import analyze_nc, reference_id
from src.services.creator.asset_references import reachable_nodes
from src.services.creator.schema_provider import get_profile, policy_for


@lru_cache(maxsize=1)
def manual_profile():
    profile = json.loads((Path(__file__).parent / "profiles" / f"{get_profile().schemaVersion}_tools.json").read_text())
    catalog = get_catalog()
    for item in profile["toolTypes"] + profile["operationTypes"]:
        if item["typeId"] not in catalog["types"]:
            raise ValueError("Manual profile contains an unknown type")
    for prop in profile["properties"]:
        field = prop["field"].split(".")[-1]
        if not any(any(f["fieldName"] == field for f in info["fields"]) for info in catalog["types"].values()):
            raise ValueError("Manual profile contains an unknown field")
    profile["hash"] = hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()
    return profile


def start(request):
    draft = request.draft.model_dump(by_alias=True)
    catalog = get_catalog()
    if request.expectedRevision != draft["revision"] or request.profileHash != manual_profile()["hash"]:
        raise CamInputError("초안 또는 공구 입력 규칙이 변경되었습니다. 다시 확인해 주세요.")
    if any(draft[key] != catalog[key] for key in ("schemaHash", "schemaVersion", "rulesVersion")):
        raise CamInputError("현재 스키마와 초안이 다릅니다.")
    return draft


def finish(draft, **extra):
    draft["revision"] += 1
    return {"ready": True, "draft": CreatorDraft.model_validate(draft).model_dump(by_alias=True), "persisted": False, **extra}


def add_node(draft, type_id, **fields):
    key = str(uuid4())
    draft["nodes"][key] = {"nodeId": key, "typeId": type_id, "fields": fields}
    return {"$node": key}


def steps(draft, wp_id):
    wp = draft["nodes"].get(wp_id)
    reachable = reachable_nodes(draft["nodes"], [draft["projectAssetNodeId"]])
    if not wp or wp["typeId"] != "Workplan" or wp_id not in reachable:
        raise CamInputError("프로젝트에 속한 워크플랜을 선택해 주세요.")
    refs = wp["fields"].get("its_elements", [])
    if not isinstance(refs, list):
        raise CamInputError("워크플랜 실행 요소 형식을 확인해 주세요.")
    result = [reference_id(ref) for ref in refs if draft["nodes"].get(reference_id(ref), {}).get("typeId") in ("MachiningWorkingstep", "TurningWorkingstep")]
    if len(result) != len(set(result)) or len(result) > 300:
        raise CamInputError("워킹스텝 개수 또는 중복을 확인해 주세요.")
    return result


def asset_for(draft, asset_id):
    asset = next((a for a in draft["assets"] if a["assetNodeId"] == asset_id and a["role"] == "tool"), None)
    if not asset or draft["nodes"].get(asset["elementNodeId"], {}).get("typeId") != "DtCuttingTool13399":
        raise CamInputError("13399 공구 자산을 선택해 주세요.")
    return asset


def definition(draft, asset_id):
    item = next((t for t in draft["manualTools"] if t["assetNodeId"] == asset_id), None)
    if not item:
        raise CamInputError("공구 직접 등록에서 내부 공구 타입과 제원을 먼저 지정해 주세요.")
    if item["toolTypeId"] not in {t["typeId"] for t in manual_profile()["toolTypes"]}:
        raise CamInputError("공구 타입 규칙을 다시 확인해 주세요.")
    return item


def values_for(draft, asset_id):
    asset = asset_for(draft, asset_id)
    props = {p["name"]: p for p in manual_profile()["properties"]}
    values = {}
    legacy = definition(draft, asset_id).get("legacyUnits", False)
    legacy_length = None
    for ref in draft["nodes"][asset["elementNodeId"]]["fields"].get("numerical_value", []):
        node = draft["nodes"].get(reference_id(ref), {})
        fields = node.get("fields", {})
        name = fields.get("value_name")
        if name == "overhang_length" and legacy:
            legacy_length = fields.get("value_component")
        if name not in props:
            continue
        try:
            value = float(fields["value_component"])
        except (ValueError, TypeError, KeyError):
            raise CamInputError("공구 수치 형식을 확인해 주세요.")
        unit = draft["nodes"].get(reference_id(fields.get("unit_component")), {}).get("fields", {}).get("unit_name")
        if unit is None and legacy:
            unit = props[name]["unit"]
        if unit != props[name]["unit"] or name in values or not math.isfinite(value) or value < props[name]["min"] or (props[name]["integer"] and not value.is_integer()):
            raise CamInputError("공구 단위·중복 항목·수치 범위를 확인해 주세요.")
        values[name] = int(value) if props[name]["integer"] else value
    if legacy_length is not None and "assembly_length" not in values:
        try:
            number = float(legacy_length)
            if not math.isfinite(number) or number < 0:
                raise ValueError()
            values["assembly_length"] = number
        except (TypeError, ValueError):
            raise CamInputError("기존 공구 전체 길이의 수치를 확인해 주세요.")
    return values


def operation_for(draft, step_id):
    operation = draft["nodes"].get(reference_id(draft["nodes"].get(step_id, {}).get("fields", {}).get("its_operation")))
    if not operation or not any(f["fieldName"] == "its_tool" for f in get_catalog()["types"].get(operation["typeId"], {}).get("fields", [])):
        raise CamInputError("워킹스텝의 가공 작업 타입을 먼저 선택해 주세요.")
    return operation


def sync_tool(draft, step_id, asset_id, overwrite=False, verify=False):
    operation = operation_for(draft, step_id)
    if any(n["nodeId"] != step_id and reference_id(n["fields"].get("its_operation")) == operation["nodeId"] for n in draft["nodes"].values()):
        raise CamInputError("여러 객체가 공유하는 가공 작업은 먼저 분리해 주세요.")
    type_id = definition(draft, asset_id)["toolTypeId"]
    tool_id = reference_id(operation["fields"].get("its_tool"))
    tool = draft["nodes"].get(tool_id)
    if tool and any(n["nodeId"] != operation["nodeId"] and reference_id(n["fields"].get("its_tool")) == tool_id for n in draft["nodes"].values()):
        raise CamInputError("여러 가공 작업이 공유하는 내부 공구는 먼저 분리해 주세요.")
    if tool and tool["typeId"] != type_id:
        raise CamInputError("내부 공구 타입이 다릅니다. 상세 편집에서 타입을 확인한 뒤 연결해 주세요.")
    if not tool:
        if verify:
            raise CamInputError("워킹스텝 내부 공구가 누락되었습니다.")
        ref = add_node(draft, type_id, its_id=f"tool_{step_id}")
        operation["fields"]["its_tool"] = ref
        tool = draft["nodes"][ref["$node"]]
    fields = {f["fieldName"] for f in get_catalog()["types"][type_id]["fields"]}
    values = values_for(draft, asset_id)
    for prop in manual_profile()["properties"]:
        name, field = prop["name"], prop["field"]
        if name not in values:
            continue
        target = tool
        if "." in field:
            parent, field = field.split(".")
            edges = tool["fields"].get(parent, [])
            if not isinstance(edges, list) or len(edges) > 1:
                raise CamInputError("복수 절삭날은 기능 길이를 직접 확인해야 합니다.")
            if not edges:
                if verify:
                    raise CamInputError("절삭날 길이 동기화가 필요합니다.")
                edges = [add_node(draft, "CuttingComponent")]
                tool["fields"][parent] = edges
            target = draft["nodes"].get(reference_id(edges[0]))
            if not target:
                raise CamInputError("절삭날 객체가 누락되었습니다.")
        elif field not in fields:
            raise CamInputError(f"선택한 공구 타입에 {prop['label']} 항목을 적용할 수 없습니다.")
        old = target["fields"].get(field)
        if old != values[name]:
            if verify or (old is not None and not overwrite):
                raise CamInputError(f"{prop['label']}: 내부 공구값과 13399 값이 다릅니다. 공구값 동기화를 확인해 주세요.")
            target["fields"][field] = values[name]


def prepare_tool(request):
    draft = start(request)
    profile = manual_profile()
    if request.toolTypeId not in {t["typeId"] for t in profile["toolTypes"]} or not request.name.strip():
        raise CamInputError("공구 이름과 타입을 확인해 주세요.")
    props = {p["name"]: p for p in profile["properties"]}
    permitted = {f["fieldName"] for f in get_catalog()["types"][request.toolTypeId]["fields"]}
    values = {}
    for name, item in request.values.items():
        prop = props.get(name)
        if not prop or prop["field"].split(".")[0] not in permitted:
            raise CamInputError("공구 타입에 없는 수치 항목입니다.")
        if item.unit not in (["mm", "in"] if prop["unit"] == "mm" else [prop["unit"]]):
            raise CamInputError("공구 수치의 단위가 올바르지 않습니다.")
        value = item.value * (25.4 if item.unit == "in" else 1)
        if not math.isfinite(value) or value < prop["min"] or (prop["integer"] and not float(value).is_integer()):
            raise CamInputError("공구 수치 범위 또는 정수 형식을 확인해 주세요.")
        values[name] = value
    if request.assetNodeId:
        asset = asset_for(draft, request.assetNodeId)
    else:
        project = draft["nodes"][draft["projectAssetNodeId"]]
        ref = add_node(draft, "DtCuttingTool13399", element_id=f"tool_{uuid4().hex[:12]}", category="CuttingTool")
        root = add_node(draft, "DtAsset", schema_version=draft["schemaVersion"], asset_global_id=project["fields"].get("asset_global_id", "https://digital-thread.re/kitech/"), id=f"tool_{uuid4().hex[:12]}", asset_kind="instance", dt_elements=[ref])
        asset = {"assetNodeId": root["$node"], "elementNodeId": ref["$node"], "role": "tool"}
        draft["assets"].append(asset)
    asset_id = asset["assetNodeId"]
    if any(l["assetNodeId"] == asset_id and l["workplanNodeId"] not in draft["manualWorkplans"] for l in draft["toolLinks"]):
        raise CamInputError("CAM/NC 자동 생성 공구는 기존 상세 편집과 NC 연결에서 수정해 주세요.")
    previous_definition = next((t for t in draft["manualTools"] if t["assetNodeId"] == asset_id), {})
    definition_item = {"assetNodeId": asset_id, "toolTypeId": request.toolTypeId, "legacyUnits": previous_definition.get("legacyUnits", False)}
    draft["manualTools"] = [t for t in draft["manualTools"] if t["assetNodeId"] != asset_id] + [definition_item]
    element = draft["nodes"][asset["elementNodeId"]]
    element["fields"]["display_name"] = request.name.strip()
    refs = element["fields"].setdefault("numerical_value", [])
    # Edit known properties in place; arbitrary detailed schema attributes stay intact.
    for name, value in values.items():
        matches = [draft["nodes"][reference_id(r)] for r in refs if draft["nodes"].get(reference_id(r), {}).get("fields", {}).get("value_name") == name]
        if len(matches) > 1:
            raise CamInputError("공구 수치가 중복되어 있습니다. 상세 편집에서 정리해 주세요.")
        if matches:
            target = matches[0]
        else:
            ref = add_node(draft, "NumericalValue", value_name=name)
            refs.append(ref)
            target = draft["nodes"][ref["$node"]]
        target["fields"]["value_component"] = str(value)
        target["fields"]["unit_component"] = add_node(draft, "Unit", unit_name=props[name]["unit"])
    for link in draft["manualToolLinks"]:
        if link["assetNodeId"] == asset_id:
            sync_tool(draft, link["stepNodeId"], asset_id, request.synchronize)
    return finish(draft, assetNodeId=asset_id)


def prepare_step(request):
    draft = start(request)
    wp_id = request.workplanNodeId
    current = steps(draft, wp_id)
    step_id = request.stepNodeId
    if request.action == "add":
        if not request.name.strip() or request.operationTypeId not in {t["typeId"] for t in manual_profile()["operationTypes"]}:
            raise CamInputError("작업 이름과 가공 타입을 선택해 주세요.")
        if len(current) >= 300 or any(draft["nodes"][s]["fields"].get("its_id") == request.name.strip() for s in current):
            raise CamInputError("워킹스텝 수 또는 중복된 이름을 확인해 주세요.")
        op = add_node(draft, request.operationTypeId, its_id=f"operation_{uuid4().hex[:12]}")
        ref = add_node(draft, "MachiningWorkingstep", its_id=request.name.strip(), its_operation=op)
        draft["nodes"][wp_id]["fields"].setdefault("its_elements", []).append(ref)
        step_id = ref["$node"]
    elif step_id not in current:
        raise CamInputError("대상 워킹스텝이 현재 워크플랜에 없습니다.")
    for node in draft["nodes"].values():
        if node["typeId"] == "Workplan" and node["nodeId"] != wp_id and any(reference_id(r) == step_id for r in node["fields"].get("its_elements", []) if isinstance(r, dict)):
            raise CamInputError("공유된 워킹스텝은 먼저 분리해 주세요.")
    if wp_id not in draft["manualWorkplans"]:
        # Conversion is opt-in; neither existing asset IDs nor original CAM fields change.
        for link in draft["toolLinks"]:
            if link["workplanNodeId"] == wp_id and link["stepNodeIds"]:
                if not request.adoptExisting:
                    raise CamInputError("기존 CAM 공구 연결을 수동 관리로 전환할지 확인해 주세요. NC 재확인이 필요합니다.")
                asset_for(draft, link["assetNodeId"])
                op = operation_for(draft, link["stepNodeIds"][0])
                tool = draft["nodes"].get(reference_id(op["fields"].get("its_tool")))
                if not tool or tool["typeId"] not in {t["typeId"] for t in manual_profile()["toolTypes"]}:
                    raise CamInputError("기존 내부 공구 타입은 수동 전환 지원 범위 밖입니다. 별도 워크플랜을 사용해 주세요.")
                if not any(t["assetNodeId"] == link["assetNodeId"] for t in draft["manualTools"]):
                    draft["manualTools"].append({"assetNodeId": link["assetNodeId"], "toolTypeId": tool["typeId"], "legacyUnits": True})
                for existing_step in link["stepNodeIds"]:
                    if existing_step not in current:
                        raise CamInputError("기존 NC 연결 순서가 변경되었습니다. 기존 연결을 먼저 확인해 주세요.")
                    draft["manualToolLinks"].append({"workplanNodeId": wp_id, "stepNodeId": existing_step, "assetNodeId": link["assetNodeId"]})
        draft["manualWorkplans"].append(wp_id)
    draft["manualToolLinks"] = [l for l in draft["manualToolLinks"] if l["stepNodeId"] != step_id]
    for link in draft["toolLinks"]:
        if link["workplanNodeId"] == wp_id:
            link["stepNodeIds"] = [s for s in link["stepNodeIds"] if s != step_id]
    if request.action != "unassign":
        asset_for(draft, request.assetNodeId)
        if any(l["assetNodeId"] == request.assetNodeId and l["workplanNodeId"] != wp_id for l in draft["manualToolLinks"]):
            raise CamInputError("다른 워크플랜에서 사용하는 공구는 별도로 등록해 주세요.")
        sync_tool(draft, step_id, request.assetNodeId, request.synchronize)
        draft["manualToolLinks"].append({"workplanNodeId": wp_id, "stepNodeId": step_id, "assetNodeId": request.assetNodeId})
    return finish(draft, stepNodeId=step_id)


def manual_snapshot(draft, wp_id):
    links = [l for l in draft["manualToolLinks"] if l["workplanNodeId"] == wp_id]
    roots = steps(draft, wp_id) + [l["assetNodeId"] for l in links]
    selected = reachable_nodes(draft["nodes"], roots)
    payload = {"nodes": {i: draft["nodes"][i] for i in sorted(selected)}, "elements": draft["nodes"][wp_id]["fields"].get("its_elements"),
               "links": links, "tools": [t for t in draft["manualTools"] if t["assetNodeId"] in roots],
               "fileLinks": [l for l in draft["fileLinks"] if l["workplanNodeId"] == wp_id and l["purpose"] == "NC"],
               "toolLinks": [l for l in draft["toolLinks"] if l["workplanNodeId"] == wp_id], "profileHash": manual_profile()["hash"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def confirmation_hash(draft, wp_id, manual):
    payload = {"snapshot": manual_snapshot(draft, wp_id), "encoding": manual.get("encoding"), "reason": manual.get("reason"), "assignments": manual.get("assignments"), "profileHash": manual.get("profileHash")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def confirm_nc(request, data):
    draft = start(request)
    wp_id = request.workplanNodeId
    current = steps(draft, wp_id)
    if not request.acknowledged or not request.reason.strip() or wp_id not in draft["manualWorkplans"]:
        raise CamInputError("수동 공구 배정과 NC 확인 사유를 입력하고 확인해 주세요.")
    analysis = analyze_nc(data, request.fileId, request.encoding)
    lines = data.decode("utf-8-sig" if request.encoding == "utf-8" else request.encoding).splitlines()
    files = [l for l in draft["fileLinks"] if l["workplanNodeId"] == wp_id and l["purpose"] == "NC"]
    if len(files) != 1 or files[0]["fileId"] != request.fileId or files[0]["sha256"] != analysis["sha256"]:
        raise CamInputError("배정된 NC 원본과 확인 요청이 다릅니다.")
    if [a.stepNodeId for a in request.assignments] != current:
        raise CamInputError("모든 워킹스텝을 현재 실행 순서대로 확인해 주세요.")
    by_step = {l["stepNodeId"]: l for l in draft["manualToolLinks"] if l["workplanNodeId"] == wp_id}
    if len(by_step) != len(current) or set(by_step) != set(current):
        raise CamInputError("모든 워킹스텝에 공구를 선택해 주세요.")
    grouped, rows, previous, previous_tag = {}, [], None, None
    for item in request.assignments:
        tag = f"T{int(item.toolTag[1:])}"
        span = (item.lineStart, item.lineEnd)
        if item.lineStart > item.lineEnd or item.lineEnd > len(lines) or (previous and span != previous and item.lineStart <= previous[1]):
            raise CamInputError("NC 구간 범위·겹침·순서를 확인해 주세요.")
        if span == previous and tag != previous_tag:
            raise CamInputError("같은 NC 구간을 공유하는 워킹스텝은 같은 T를 사용해야 합니다.")
        previous = span
        previous_tag = tag
        asset_id = by_step[item.stepNodeId]["assetNodeId"]
        sync_tool(draft, item.stepNodeId, asset_id, verify=True)
        if tag in grouped and grouped[tag]["assetNodeId"] != asset_id:
            raise CamInputError("같은 워크플랜의 동일 T는 같은 공구를 선택해야 합니다.")
        if any(l["assetNodeId"] == asset_id and t != tag for t, l in grouped.items()):
            raise CamInputError("한 공구 자산에 서로 다른 T를 배정할 수 없습니다.")
        grouped.setdefault(tag, {"workplanNodeId": wp_id, "toolTag": tag, "assetNodeId": asset_id, "stepNodeIds": []})["stepNodeIds"].append(item.stepNodeId)
        rows.append({**item.model_dump(), "toolTag": tag, "assetNodeId": asset_id})
    draft["toolLinks"] = [l for l in draft["toolLinks"] if l["workplanNodeId"] != wp_id] + list(grouped.values())
    manual = {"version": 1, "mode": "manual", "encoding": request.encoding, "reason": request.reason.strip(), "assignments": rows,
              "profileHash": manual_profile()["hash"], "analyzerSupported": analysis["supported"], "diagnostics": analysis["diagnostics"]}
    manual["snapshotHash"] = confirmation_hash(draft, wp_id, manual)
    draft["ncReviews"] = [r for r in draft["ncReviews"] if r["workplanNodeId"] != wp_id] + [{"workplanNodeId": wp_id, "fileId": request.fileId, "sha256": analysis["sha256"], "stepNodeIds": current, "manual": manual}]
    return finish(draft, confirmation=manual)


def resolve_manual(draft, target_ids, make_node):
    allowed, issues = set(), []
    project_requested = draft["projectAssetNodeId"] in target_ids
    for wp_id in draft["manualWorkplans"]:
        links = [l for l in draft["manualToolLinks"] if l["workplanNodeId"] == wp_id]
        if not project_requested and not any(l["assetNodeId"] in target_ids for l in links):
            continue
        try:
            current = steps(draft, wp_id)
            if not current:
                continue
            if len(links) != len(current) or {l["stepNodeId"] for l in links} != set(current):
                raise CamInputError("모든 워킹스텝에 수동 공구 연결을 확인해 주세요.")
            reviews = [r for r in draft["ncReviews"] if r["workplanNodeId"] == wp_id]
            review = reviews[0] if len(reviews) == 1 else None
            if not review or not review.get("manual") or review["manual"].get("snapshotHash") != confirmation_hash(draft, wp_id, review["manual"]):
                raise CamInputError("NC 수동 확인이 필요합니다. 입력 변경 후 다시 확인해 주세요.")
            files = [l for l in draft["fileLinks"] if l["workplanNodeId"] == wp_id and l["purpose"] == "NC"]
            if len(files) != 1 or any(review[k] != files[0][k] for k in ("fileId", "sha256")) or review["stepNodeIds"] != current:
                raise CamInputError("NC 파일과 워킹스텝 순서를 다시 확인해 주세요.")
            for link in links:
                sync_tool(draft, link["stepNodeId"], link["assetNodeId"], verify=True)
                asset = asset_for(draft, link["assetNodeId"])
                root, element = draft["nodes"][asset["assetNodeId"]], draft["nodes"][asset["elementNodeId"]]
                identity = (root["fields"].get("asset_global_id"), root["fields"].get("id"), element["fields"].get("element_id"))
                if not all(isinstance(v, str) and v.strip() for v in identity):
                    raise CamInputError("공구 글로벌 ID·자산 ID·요소 ID를 입력해 주세요.")
                identity = tuple(v.strip() for v in identity)
                fullpath = f'{identity[0].rstrip("/")}/{identity[1]}/{identity[2]}'
                for other in draft["assets"]:
                    if other["assetNodeId"] == asset["assetNodeId"]:
                        continue
                    other_root = draft["nodes"].get(other["assetNodeId"], {}).get("fields", {})
                    other_element = draft["nodes"].get(other["elementNodeId"], {}).get("fields", {})
                    values = (other_root.get("asset_global_id"), other_root.get("id"), other_element.get("element_id"))
                    if all(isinstance(v, str) for v in values) and f'{values[0].strip().rstrip("/")}/{values[1].strip()}/{values[2].strip()}' == fullpath:
                        raise CamInputError("공구 참조 주소가 다른 자산과 중복됩니다. 자산 ID를 구분해 주세요.")
                from urllib.parse import urlsplit
                uri = urlsplit(identity[0])
                if uri.scheme not in ("http", "https") or not uri.netloc or uri.query or uri.fragment:
                    raise CamInputError("공구 글로벌 ID 주소를 확인해 주세요.")
                op = operation_for(draft, link["stepNodeId"])
                policy = next((p for p in get_profile().referencePolicies if p.targetRole == "tool" and policy_for(op["typeId"], p.fieldName) == p), None)
                if policy is None:
                    raise CamInputError("가공 타입의 공구 참조 정책이 없습니다.")
                if policy.fieldName in op["fields"]:
                    raise CamInputError("수동 XML 참조와 공구 선택을 동시에 사용할 수 없습니다.")
                ref = make_node(get_profile().referenceType, {"element_id": f"tool-ref-{op['nodeId']}", "category": "reference", "keys": [make_node(get_profile().keyValueType, {"key": policy.key, "value": fullpath})]})
                op["fields"][policy.fieldName] = ref
                allowed.add((op["nodeId"], policy.fieldName))
            issues.append({"nodeId": wp_id, "fieldName": None, "itemId": None, "code": "NC_MANUAL_CONFIRMATION", "severity": "warning", "message": "NC 구간·T·공구는 작업자가 수동 확인했습니다. NC 의미·가공 안전성은 검증하지 않았습니다."})
        except (CamInputError, KeyError, TypeError, ValueError, AttributeError) as exc:
            issues.append({"nodeId": wp_id, "fieldName": None, "itemId": None, "code": "MANUAL_TOOL_INVALID", "severity": "error", "message": str(exc)})
    return allowed, issues
