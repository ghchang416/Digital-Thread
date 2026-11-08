"""Missing-only completion for staged ELS candidates, with explicit tool synchronization."""
from src.schemas.creator import CreatorDraft
from src.schemas.creator_completion import CompletionRequest
from src.schemas.creator_els import ElsCandidate, ElsOrigin
from src.schemas.creator_manual import ManualToolRequest, ToolInput
from src.services.creator.asset_references import reachable_nodes
from src.services.creator.completion import complete_workplan
from src.services.creator.manual import manual_profile, prepare_tool, sync_tool, values_for
from .contracts import check_request_budget, validate_candidate_metadata
from .profile import load_profile


def complete(request):
    check_request_budget(request.model_dump(by_alias=True))
    candidate = request.candidate.model_copy(deep=True)
    validate_candidate_metadata(candidate.draft, candidate.metadata)
    wp = next((w for w in candidate.metadata.elsWorkplans if w.workplanNodeId == request.workplanNodeId), None)
    if wp is None:
        raise ValueError("ELS_COMPLETION_SCOPE")
    original = candidate.draft.model_dump(by_alias=True)
    draft = candidate.draft.model_dump(by_alias=True)
    project = next(a for a in draft["assets"] if a["assetNodeId"] == draft["projectAssetNodeId"])
    pieces = draft["nodes"][project["elementNodeId"]]["fields"].get("its_workpieces", [])
    for step in wp.steps:
        fields = draft["nodes"][step.stepNodeId]["fields"]
        feature = draft["nodes"].get(fields.get("its_feature", {}).get("$node"))
        operation = draft["nodes"].get(fields.get("its_operation", {}).get("$node"))
        if not feature or feature["typeId"] != "ToolpathFeature" or not operation or operation["typeId"] != "FreeformOperation":
            raise ValueError("ELS_TEMPLATE_UNSUPPORTED")
        if "its_workpiece" not in feature["fields"]:
            if len(pieces) != 1 or draft["nodes"].get(pieces[0].get("$node"), {}).get("typeId") != "Workpiece":
                raise ValueError("ELS_PROJECT_WORKPIECE_REQUIRED")
            feature["fields"]["its_workpiece"] = dict(pieces[0])
        elif feature["fields"]["its_workpiece"] not in pieces:
            raise ValueError("ELS_PROJECT_WORKPIECE_REQUIRED")
    links = [l for l in candidate.metadata.elsToolLinks if l.workplanNodeId == wp.workplanNodeId]
    props = {p["field"]: p for p in manual_profile()["properties"]}
    defaults = load_profile()[0].defaults
    for asset_id in dict.fromkeys(l.assetNodeId for l in links):
        definition = next(d for d in draft["manualTools"] if d["assetNodeId"] == asset_id)
        if definition["toolTypeId"] != "MillingCuttingTool" or definition.get("legacyUnits"):
            raise ValueError("ELS_TOOL_TEMPLATE_UNSUPPORTED")
        values = values_for(draft, asset_id)
        missing = {props[d.field]["name"]: ToolInput(value=d.value, unit=props[d.field]["unit"])
                   for d in defaults if d.typeId == "MillingCuttingTool" and props[d.field]["name"] not in values}
        if missing and request.includePlaceholders:
            result = prepare_tool(ManualToolRequest(draft=CreatorDraft.model_validate(draft), expectedRevision=draft["revision"],
                profileHash=manual_profile()["hash"], assetNodeId=asset_id, name="ELS tool", toolTypeId="MillingCuttingTool", values=missing))
            # Do not rename an existing tool during missing-only completion.
            asset = next(a for a in draft["assets"] if a["assetNodeId"] == asset_id)
            name = draft["nodes"][asset["elementNodeId"]]["fields"].get("display_name")
            draft = result["draft"]
            if name is None:
                draft["nodes"][asset["elementNodeId"]]["fields"].pop("display_name", None)
            else:
                draft["nodes"][asset["elementNodeId"]]["fields"]["display_name"] = name
        for link in (l for l in links if l.assetNodeId == asset_id):
            sync_tool(draft, link.stepNodeId, asset_id, overwrite=request.synchronizeTools)
    reachable = reachable_nodes(draft["nodes"], [wp.workplanNodeId])
    referenced = [l["targetAssetNodeId"] for l in draft["referenceLinks"] if l["sourceNodeId"] in reachable]
    reachable |= reachable_nodes(draft["nodes"], referenced)
    if request.includePlaceholders:
        for node_id in reachable:
            node = draft["nodes"][node_id]
            for default in defaults:
                if default.typeId == {"DtMaterial": "Material"}.get(node["typeId"], node["typeId"]) and default.field not in node["fields"]:
                    node["fields"][default.field] = default.value
    result = complete_workplan(CompletionRequest(draft=CreatorDraft.model_validate(draft), workplanNodeId=wp.workplanNodeId,
        includePlaceholders=request.includePlaceholders))
    draft = result["draft"]
    draft["revision"] = original["revision"]
    changed = []
    for node_id, node in draft["nodes"].items():
        for field, value in node["fields"].items():
            old = original["nodes"].get(node_id, {}).get("fields", {})
            if field not in old or old[field] != value:
                changed.append((node_id, field, value))
    for node_id, field, value in changed:
        entry = next((e for e in draft["completionEntries"] if e["nodeId"] == node_id and e["fieldName"] == field and e["value"] == value), None)
        kind = entry["kind"] if entry else "placeholder"
        if field == "its_workpiece":
            kind = "generated"
        if node_id in original["nodes"] and field in original["nodes"][node_id]["fields"]:
            kind = "manual"
        candidate.metadata.elsOrigins.append(ElsOrigin(importEntryId=wp.importEntryId, nodeId=node_id, fieldName=field,
            kind=kind, appliedValue=value, sources=[], rule="els-completion-1",
            reason=entry["reason"] if entry else "Explicit ELS missing-value completion or confirmed tool synchronization; verify before machining."))
    candidate.draft = CreatorDraft.model_validate(draft)
    if changed:
        candidate.metadata.elsReviews = [r for r in candidate.metadata.elsReviews if r.workplanNodeId != wp.workplanNodeId]
    candidate = ElsCandidate.model_validate(candidate.model_dump(by_alias=True))
    validate_candidate_metadata(candidate.draft, candidate.metadata)
    return candidate
