"""Stateless NC analysis and workplan-local tool compilation using legacy helpers."""
import dataclasses
import hashlib
import math
import re
from enum import Enum
from uuid import uuid4

from xsdata.formats.dataclass.parsers import XmlParser
from src.services.creator.schema_provider import get_model, get_profile
from src.schemas.creator import CreatorDraft
from src.services.creator.cam import CamInputError
from src.services.creator.catalog import get_catalog
from src.utils.cam_common import F14649_TO_13399, build_cutting_tool_13399_dtasset_xml
from src.utils.nc_spliter import extract_tool_changes, _strip_comments

PROPERTIES = {path.split(".")[-1]: name for path, name in F14649_TO_13399.items()}


def analyze_nc(data: bytes, file_id: str, encoding="utf-8"):
    if not data or len(data) > 8 * 1024 * 1024:
        raise CamInputError("NC 파일은 비어 있지 않은 8 MiB 이하 파일이어야 합니다.")
    try:
        content = data.decode("utf-8-sig" if encoding == "utf-8" else encoding)
    except UnicodeError as exc:
        raise CamInputError("NC 인코딩이 맞지 않습니다. UTF-8 또는 CP949를 선택해 주세요.") from exc
    if "\x00" in content:
        raise CamInputError("텍스트 NC 파일을 선택해 주세요.")
    raw_lines = content.splitlines()
    if len(raw_lines) > 100000 or any(len(line) > 4096 for line in raw_lines):
        raise CamInputError("NC 줄 수 또는 한 줄 길이 제한을 초과했습니다.")
    diagnostics, lines = [], []
    for number, raw in enumerate(raw_lines, 1):
        # Keep source line numbers, and normalize compact words for the existing extractor.
        code = _strip_comments(raw)
        code = re.sub(r"(?<=\d)(?=[A-Za-z])", " ", code)
        lines.append(code)
        if "(" in code or ")" in code or re.search(r"[#\[\]]|\b(?:M0?98|M0?99)\b", code, re.I):
            diagnostics.append(f"{number}행: 매크로·서브프로그램·복합 주석은 자동 연결 지원 범위 밖입니다.")
        if len(re.findall(r"\bT\d+\b", code, re.I)) > 1:
            diagnostics.append(f"{number}행: 한 블록의 복수 T 지정은 직접 확인이 필요합니다.")
        if re.search(r"\bT\d+\.", code, re.I) or len(re.findall(r"\bM0?6\b", code, re.I)) > 1:
            diagnostics.append(f"{number}행: 비정수 T 번호 또는 복수 M6 블록은 지원하지 않습니다.")
    events = sorted(extract_tool_changes("\n".join(lines)), key=lambda item: item["line"])
    detected = [event["line"] for event in events]
    changes = [i + 1 for i, line in enumerate(lines) if re.search(r"\bM0?6\b", line, re.I)]
    if len(set(detected)) != len(detected) or set(changes) != set(detected):
        diagnostics.append("공구 교환 M6와 T 번호의 대응이 불명확합니다. 자동 연결을 차단했습니다.")
    if not events:
        diagnostics.append("지원하는 T/M6 공구 교환 구간을 찾지 못했습니다.")
    if len(events) > 300:
        raise CamInputError("한 NC 파일에서 최대 300개 공구 교환을 지원합니다.")
    digest = hashlib.sha256(data).hexdigest()
    return {"fileId": file_id, "sha256": digest, "encoding": encoding, "analyzerVersion": "legacy-tool-events-creator-1",
            "events": [{"eventId": f'{digest[:24]}-{index}-{event["line"]}', "toolTag": event["tool"],
                        "lineStart": event["line"], "lineEnd": events[index + 1]["line"] - 1 if index + 1 < len(events) else len(raw_lines),
                        "source": raw_lines[event["line"] - 1]} for index, event in enumerate(events)],
            "diagnostics": list(dict.fromkeys(diagnostics)), "supported": not diagnostics, "persisted": False}


def reference_id(value):
    return value.get("$node") if isinstance(value, dict) else None


def tool_nodes(nodes, step_id):
    operation = nodes.get(reference_id(nodes.get(step_id, {}).get("fields", {}).get("its_operation")))
    tool = nodes.get(reference_id(operation["fields"].get("its_tool"))) if operation else None
    if not tool:
        raise CamInputError("워킹스텝의 가공 작업과 공구 객체를 먼저 입력해 주세요.")
    return operation, tool


def tool_values(nodes, step_id):
    _, tool = tool_nodes(nodes, step_id)
    values = {}
    for field, name in PROPERTIES.items():
        if field == "tool_functional_length":
            edges = tool["fields"].get("its_cutting_edges", [])
            if not isinstance(edges, list):
                raise CamInputError("절삭날 목록 형식을 확인해 주세요.")
            if len(edges) > 1:
                raise CamInputError("복수 절삭날 공구는 가공부 길이를 하나로 확정하는 규칙이 필요합니다.")
            edge = nodes.get(reference_id(edges[0])) if edges else None
            value = edge["fields"].get(field) if edge else None
        else:
            value = tool["fields"].get(field)
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise CamInputError(f"공구 {name} 값은 0 이상의 유한한 숫자여야 합니다.")
            if name == "number_of_teeth" and not float(value).is_integer():
                raise CamInputError("공구 날 수는 정수여야 합니다.")
            values[name] = value
    return values


def asset_values(nodes, asset):
    element = nodes[asset["elementNodeId"]]
    values = {}
    for ref in element["fields"].get("numerical_value", []):
        node = nodes.get(reference_id(ref))
        if node and node["fields"].get("value_name") in PROPERTIES.values():
            try:
                name = node["fields"]["value_name"]
                value = float(node["fields"].get("value_component", ""))
                if name in values or not math.isfinite(value) or value < 0:
                    raise ValueError()
                values[name] = value
            except (ValueError, TypeError) as exc:
                raise CamInputError("13399 공구 수치의 중복·형식을 확인해 주세요.") from exc
    return values


def to_graph(instance, nodes):
    if isinstance(instance, Enum):
        return instance.value
    if not dataclasses.is_dataclass(instance):
        return instance
    node_id = str(uuid4())
    fields = {}
    nodes[node_id] = {"nodeId": node_id, "typeId": type(instance).__name__, "fields": fields}
    for field in dataclasses.fields(instance):
        value = getattr(instance, field.name)
        if value is None or value == []:
            continue
        if isinstance(value, list):
            fields[field.name] = [to_graph(item, nodes) if dataclasses.is_dataclass(item) else {"itemId": str(uuid4()), "value": to_graph(item, nodes)} for item in value]
        else:
            fields[field.name] = to_graph(value, nodes)
    return {"$node": node_id}


def sync_step_values(nodes, step_id, values):
    _, tool = tool_nodes(nodes, step_id)
    catalog = get_catalog()
    for field, name in PROPERTIES.items():
        if name not in values:
            continue
        target = tool
        if field == "tool_functional_length":
            if not any(f["fieldName"] == "its_cutting_edges" for f in catalog["types"][tool["typeId"]]["fields"]):
                raise CamInputError("선택한 공구 타입에 절삭날 길이를 적용할 수 없습니다.")
            edges = tool["fields"].get("its_cutting_edges", [])
            if not edges:
                edge = {"nodeId": str(uuid4()), "typeId": "CuttingComponent", "fields": {}}
                nodes[edge["nodeId"]] = edge
                edges = [{"$node": edge["nodeId"]}]
                tool["fields"]["its_cutting_edges"] = edges
            target = nodes[reference_id(edges[0])]
        if not any(f["fieldName"] == field for f in catalog["types"][target["typeId"]]["fields"]):
            raise CamInputError(f"선택한 공구 타입에 {field}를 적용할 수 없습니다.")
        value = values[name]
        if name == "number_of_teeth":
            if not float(value).is_integer():
                raise CamInputError("공구 날 수는 정수여야 합니다.")
            value = int(value)
        target["fields"][field] = value


def compile_tools(request, data):
    try:
        return _compile_tools(request, data)
    except (KeyError, TypeError, AttributeError, IndexError) as exc:
        raise CamInputError("워크플랜·공구 객체의 연결 또는 값 형식이 올바르지 않습니다.") from exc


def _compile_tools(request, data):
    catalog = get_catalog()
    draft = request.draft.model_dump(by_alias=True)
    if request.workplanNodeId in draft["manualWorkplans"]:
        raise CamInputError("직접 등록한 공구는 수동 NC 확인에서 연결해 주세요. 기존 공구를 자동 생성으로 덮어쓰지 않습니다.")
    if draft["schemaHash"] != catalog["schemaHash"] or draft["rulesVersion"] != catalog["rulesVersion"]:
        raise CamInputError("현재 스키마로 다시 확인해 주세요.")
    analysis = analyze_nc(data, request.fileId, request.encoding)
    if not analysis["supported"]:
        raise CamInputError(" / ".join(analysis["diagnostics"]))
    nodes, assets = draft["nodes"], draft["assets"]
    wp = nodes.get(request.workplanNodeId)
    if not wp or wp["typeId"] != "Workplan":
        raise CamInputError("대상 워크플랜을 찾을 수 없습니다.")
    file_links = [link for link in draft["fileLinks"] if link["workplanNodeId"] == request.workplanNodeId and link["purpose"] == "NC"]
    if len(file_links) != 1 or file_links[0]["assetNodeId"] != request.fileAssetNodeId or file_links[0]["fileId"] != request.fileId or file_links[0]["sha256"] != analysis["sha256"]:
        raise CamInputError("워크플랜에 배정한 NC 원본과 요청 파일이 일치하지 않습니다.")
    steps = [reference_id(ref) for ref in wp["fields"].get("its_elements", [])]
    steps = [step for step in steps if nodes.get(step, {}).get("typeId") in ("MachiningWorkingstep", "TurningWorkingstep")]
    if [item.stepNodeId for item in request.assignments] != steps or len(set(steps)) != len(steps):
        raise CamInputError("현재 워크플랜의 모든 워킹스텝을 실행 순서대로 연결해 주세요.")
    events = {event["eventId"]: (index, event) for index, event in enumerate(analysis["events"])}
    if any(item.eventId not in events for item in request.assignments):
        raise CamInputError("NC 구간이 변경되었습니다. 다시 분석해 주세요.")
    order = [events[item.eventId][0] for item in request.assignments]
    if order != sorted(order) or set(order) != set(range(len(events))):
        raise CamInputError("NC의 모든 구간에 연속된 워킹스텝을 실행 순서대로 연결해 주세요.")
    grouped = {}
    for item in request.assignments:
        tag = events[item.eventId][1]["toolTag"]
        grouped.setdefault(tag, []).append(item.stepNodeId)
    old_links = {link["toolTag"]: link for link in draft["toolLinks"] if link["workplanNodeId"] == request.workplanNodeId}
    if len(old_links) != sum(link["workplanNodeId"] == request.workplanNodeId for link in draft["toolLinks"]):
        raise CamInputError("중복 공구 연결이 있습니다.")
    by_asset = {asset["assetNodeId"]: asset for asset in assets}
    file_asset = by_asset.get(request.fileAssetNodeId)
    if not file_asset or file_asset["role"] != "file" or nodes.get(file_asset["elementNodeId"], {}).get("typeId") != "DtFile":
        raise CamInputError("등록된 dt_file 자산을 찾을 수 없습니다.")
    for tag, old in old_links.items():
        asset = by_asset.get(old["assetNodeId"])
        if not asset or asset["role"] != "tool" or nodes.get(asset["elementNodeId"], {}).get("typeId") != "DtCuttingTool13399":
            raise CamInputError("기존 13399 공구 자산이 누락되었습니다.")
        if any(link["assetNodeId"] == old["assetNodeId"] and (link["workplanNodeId"] != request.workplanNodeId or link["toolTag"] != tag) for link in draft["toolLinks"]):
            raise CamInputError("공구 자산은 한 워크플랜의 한 T 번호에만 연결할 수 있습니다.")
    merged, conflicts = {}, []
    for tag, step_ids in grouped.items():
        sources = [{"label": str(nodes[step]["fields"].get("its_id", step)), "values": tool_values(nodes, step)} for step in step_ids]
        old = old_links.get(tag)
        if old and old["assetNodeId"] in by_asset:
            sources.append({"label": "현재 13399 공구", "values": asset_values(nodes, by_asset[old["assetNodeId"]])})
        values = {}
        for name in PROPERTIES.values():
            choices = list(dict.fromkeys(source["values"][name] for source in sources if name in source["values"]))
            if len(choices) == 1:
                values[name] = choices[0]
            elif len(choices) > 1:
                selected = request.resolutions.get(tag, {}).get(name)
                if selected in choices:
                    values[name] = selected
                else:
                    conflicts.append({"toolTag": tag, "property": name, "choices": [{"label": source["label"], "value": source["values"][name]} for source in sources if name in source["values"]]})
        if not values and not any(conflict["toolTag"] == tag for conflict in conflicts):
            raise CamInputError("공구 사양이 없습니다. CAM 공구값을 먼저 입력해 주세요.")
        merged[tag] = values
    if conflicts:
        return {"ready": False, "conflicts": conflicts, "persisted": False}
    # Retain ownership for unused T numbers so removing/re-adding an NC tool never duplicates it.
    new_links = [{**link, "stepNodeIds": []} for tag, link in old_links.items() if tag not in grouped]
    project = nodes.get(draft["projectAssetNodeId"])
    if not project or project["typeId"] != "DtAsset":
        raise CamInputError("프로젝트 자산이 누락되었습니다.")
    for tag, step_ids in grouped.items():
        values = merged[tag]
        old = old_links.get(tag)
        if old and old["assetNodeId"] in by_asset:
            asset = by_asset[old["assetNodeId"]]
            element = nodes[asset["elementNodeId"]]
            if element["typeId"] != "DtCuttingTool13399" or element["fields"].get("element_id") != tag:
                raise CamInputError("생성된 공구의 타입 또는 T 식별자가 변경되었습니다.")
            refs = element["fields"].setdefault("numerical_value", [])
            for name, value in values.items():
                target = next((nodes[reference_id(ref)] for ref in refs if nodes[reference_id(ref)]["fields"].get("value_name") == name), None)
                if target is None:
                    target = {"nodeId": str(uuid4()), "typeId": "NumericalValue", "fields": {"value_name": name}}
                    nodes[target["nodeId"]] = target
                    refs.append({"$node": target["nodeId"]})
                target["fields"]["value_component"] = str(value)
        else:
            _, tool = tool_nodes(nodes, step_ids[0])
            xml = build_cutting_tool_13399_dtasset_xml(global_asset_id_url=str(project["fields"].get("asset_global_id", "")),
                asset_id=f'tools_{request.workplanNodeId}', element_id=tag,
                display_name=str(tool["fields"].get("its_id", tag)), values_13399=values)
            ref = to_graph(XmlParser().from_string(xml, getattr(get_model(), get_profile().assetType)), nodes)
            asset = {"assetNodeId": ref["$node"], "elementNodeId": nodes[ref["$node"]]["fields"]["dt_elements"][0]["$node"], "role": "tool"}
            assets.append(asset)
        for step in step_ids:
            sync_step_values(nodes, step, values)
        new_links.append({"workplanNodeId": request.workplanNodeId, "toolTag": tag, "assetNodeId": asset["assetNodeId"], "stepNodeIds": step_ids})
    draft["toolLinks"] = [link for link in draft["toolLinks"] if link["workplanNodeId"] != request.workplanNodeId] + new_links
    draft["ncReviews"] = [review for review in draft["ncReviews"] if review["workplanNodeId"] != request.workplanNodeId] + [{"workplanNodeId": request.workplanNodeId, "fileId": request.fileId, "sha256": analysis["sha256"], "stepNodeIds": steps}]
    draft["revision"] += 1
    # DTO validation also enforces graph/node bounds before returning an atomic replacement.
    validated = CreatorDraft.model_validate(draft)
    return {"ready": True, "draft": validated.model_dump(by_alias=True), "conflicts": [], "persisted": False}
