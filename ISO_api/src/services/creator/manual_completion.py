"""Opt-in manual completion; preserve inputs and keep standalone tool values consistent."""
from copy import deepcopy

from src.schemas.creator import CreatorDraft
from src.schemas.creator_completion import CompletionRequest
from src.services.creator.cam import CamInputError
from src.services.creator.completion import complete_workplan
from src.services.creator.manual import (
    start, steps, asset_for, definition, values_for, operation_for,
    manual_profile, sync_tool, add_node,
)
from src.services.creator.nc import reference_id


def complete_manual(request):
    draft = start(request)
    original = deepcopy(draft)
    wp_id = request.workplanNodeId
    if wp_id not in draft["manualWorkplans"]:
        raise CamInputError("직접 작성한 워크플랜을 선택해 주세요.")
    selected = request.stepNodeIds if request.stepNodeIds is not None else steps(draft, wp_id)
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= set(steps(draft, wp_id)):
        raise CamInputError("현재 워크플랜의 보완 대상을 확인해 주세요.")
    links = [l for l in draft["manualToolLinks"] if l["stepNodeId"] in selected and l["workplanNodeId"] == wp_id]
    if {l["stepNodeId"] for l in links} != set(selected):
        raise CamInputError("보완할 워킹스텝에 사용 공구를 연결해 주세요.")
    asset_ids = {l["assetNodeId"] for l in links}
    related = [l for l in draft["manualToolLinks"] if l["assetNodeId"] in asset_ids]
    if any(l["workplanNodeId"] != wp_id for l in related):
        raise CamInputError("다른 워크플랜과 공유된 공구는 분리 후 보완해 주세요.")
    properties = [p for p in manual_profile()["properties"] if "." not in p["field"]]
    provenance = {}
    # Reuse an existing internal value before introducing a placeholder for a shared tool.
    for asset_id in asset_ids:
        values = values_for(draft, asset_id)
        for prop in properties:
            supplied = []
            for link in (l for l in related if l["assetNodeId"] == asset_id):
                op = operation_for(draft, link["stepNodeId"])
                tool = draft["nodes"].get(reference_id(op["fields"].get("its_tool")))
                if tool and prop["field"] in tool["fields"]:
                    supplied.append((tool["fields"][prop["field"]], tool["nodeId"]))
            if not supplied or prop["name"] in values:
                continue
            if any(v != supplied[0][0] for v, _ in supplied):
                raise CamInputError(f"{prop['label']}: 같은 공구의 기존 제원이 다릅니다. 직접 확인해 주세요.")
            value, node_id = supplied[0]
            _put_property(draft, asset_id, prop, value, provenance, node_id)
        values_for(draft, asset_id)
    for link in related:
        sync_tool(draft, link["stepNodeId"], link["assetNodeId"])
    result = complete_workplan(CompletionRequest(draft=CreatorDraft.model_validate(draft), workplanNodeId=wp_id,
        includePlaceholders=request.includePlaceholders, overrides=request.overrides), step_ids=selected)
    draft = result["draft"]
    for link in links:
        asset_id = link["assetNodeId"]
        op = operation_for(draft, link["stepNodeId"])
        tool = draft["nodes"][reference_id(op["fields"]["its_tool"])]
        values = values_for(draft, asset_id)
        for prop in properties:
            if prop["name"] not in values and prop["field"] in tool["fields"]:
                _put_property(draft, asset_id, prop, tool["fields"][prop["field"]], provenance, tool["nodeId"])
                values[prop["name"]] = tool["fields"][prop["field"]]
    for link in related:
        sync_tool(draft, link["stepNodeId"], link["assetNodeId"])
        sync_tool(draft, link["stepNodeId"], link["assetNodeId"], verify=True)
    # Record both the 13399 value and newly synchronized inline fields, outside XML.
    entries = {(e["nodeId"], e["fieldName"]): e for e in draft["completionEntries"]}
    for node_id, field, source in provenance.values():
        entries[node_id, field] = {**source, "nodeId": node_id, "fieldName": field,
                                  "value": draft["nodes"][node_id]["fields"][field]}
    for link in related:
        op = operation_for(draft, link["stepNodeId"])
        tool = draft["nodes"][reference_id(op["fields"]["its_tool"])]
        before = original["nodes"].get(tool["nodeId"], {}).get("fields", {})
        for prop in properties:
            source = provenance.get((link["assetNodeId"], prop["name"]))
            if source and prop["field"] not in before and prop["field"] in tool["fields"]:
                entries[tool["nodeId"], prop["field"]] = {**source[2], "nodeId": tool["nodeId"],
                    "fieldName": prop["field"], "value": tool["fields"][prop["field"]]}
    draft["completionEntries"] = list(entries.values())
    changed = draft["nodes"] != original["nodes"] or draft["completionEntries"] != original["completionEntries"]
    draft["revision"] = original["revision"] + int(changed)
    if changed:
        draft["ncReviews"] = [r for r in draft["ncReviews"] if r["workplanNodeId"] != wp_id]
    added = sum(e not in original["completionEntries"] for e in draft["completionEntries"])
    return {**result, "draft": CreatorDraft.model_validate(draft).model_dump(by_alias=True), "addedCount": added}


def _put_property(draft, asset_id, prop, value, provenance, source_id):
    if definition(draft, asset_id).get("legacyUnits"):
        raise CamInputError("기존 단위 없는 공구는 제원·단위를 직접 확인한 후 보완해 주세요.")
    asset = asset_for(draft, asset_id)
    element = draft["nodes"][asset["elementNodeId"]]
    refs = element["fields"].setdefault("numerical_value", [])
    if any(draft["nodes"].get(reference_id(r), {}).get("fields", {}).get("value_name") == prop["name"] for r in refs):
        raise CamInputError("공구 항목이 중복되거나 비어 있습니다. 기존 제원을 확인해 주세요.")
    unit = add_node(draft, "Unit", unit_name=prop["unit"])
    ref = add_node(draft, "NumericalValue", value_name=prop["name"], value_component=str(value), unit_component=unit)
    refs.append(ref)
    source = next((e for e in reversed(draft["completionEntries"]) if e["nodeId"] == source_id
        and e["fieldName"] == prop["field"] and e["value"] == value), None)
    source = deepcopy(source) if source else dict(kind="batch", rule="manual-tool-completion-1",
        reason="기존 내부 공구 제원을 13399 공구에 반영했습니다. 실제 사양을 확인해 주세요.")
    provenance[asset_id, prop["name"]] = (ref["$node"], "value_component", source)
