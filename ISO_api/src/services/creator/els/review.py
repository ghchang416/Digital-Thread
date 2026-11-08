"""ELS evidence and derived references, scoped to the requested authoring assets."""
import hashlib
import json
from urllib.parse import urlsplit

from src.schemas.creator import CreatorDraft
from src.schemas.creator_els import ElsCandidate, ElsReview
from src.services.creator.asset_references import reachable_nodes
from src.services.creator.manual import add_node, operation_for, sync_tool, values_for, manual_profile
from src.services.creator.preview import preview_assets
from src.services.creator.references import resolve_references
from src.services.creator.schema_provider import get_profile, policy_for
from .contracts import check_request_budget, validate_candidate_metadata
from .profile import load_profile, numeric_candidate
from .tool_identity import group_source_tools


def _identity(draft, asset_id):
    asset = next((a for a in draft["assets"] if a["assetNodeId"] == asset_id), None)
    if not asset:
        raise ValueError("ELS_REFERENCE_ASSET_MISSING")
    root, element = draft["nodes"][asset_id], draft["nodes"][asset["elementNodeId"]]
    identity = [root["fields"].get("asset_global_id"), root["fields"].get("id"), element["fields"].get("element_id")]
    if not all(isinstance(v, str) and v.strip() for v in identity):
        raise ValueError("ELS_REFERENCE_IDENTITY_REQUIRED")
    global_id, asset_name, element_id = (v.strip() for v in identity)
    uri = urlsplit(global_id)
    if uri.scheme not in {"http", "https"} or not uri.netloc or uri.query or uri.fragment or uri.username or uri.password or any(c.isspace() for c in global_id):
        raise ValueError("ELS_REFERENCE_URI_INVALID")
    path = f"{global_id.rstrip('/')}/{asset_name}/{element_id}"
    for other in draft["assets"]:
        if other["assetNodeId"] == asset_id:
            continue
        fields = draft["nodes"][other["assetNodeId"]]["fields"]
        element_fields = draft["nodes"][other["elementNodeId"]]["fields"]
        other_values = [fields.get("asset_global_id"), fields.get("id"), element_fields.get("element_id")]
        if all(isinstance(v, str) for v in other_values) and path == "/".join([other_values[0].strip().rstrip("/"), *[v.strip() for v in other_values[1:]]]):
            raise ValueError("ELS_DUPLICATE_ASSET_IDENTITY")
    return asset, path


def _scoped(candidate, targets):
    project_requested = candidate.draft.projectAssetNodeId in targets
    wps = candidate.metadata.elsWorkplans if project_requested else []
    tools = {l.assetNodeId for l in candidate.metadata.elsToolLinks if l.workplanNodeId in {wp.workplanNodeId for wp in wps}}
    origin_nodes = {o.nodeId for o in candidate.metadata.elsOrigins}
    raw = candidate.draft.model_dump(by_alias=True)
    tools.update(a.assetNodeId for a in candidate.draft.assets if a.role == "tool" and a.assetNodeId in targets and
                 reachable_nodes(raw["nodes"], [a.assetNodeId]) & origin_nodes)
    return wps, tools


def _check(candidate, targets):
    draft, metadata = candidate.draft, candidate.metadata
    validate_candidate_metadata(draft, metadata)
    if candidate.request.profileHash != load_profile()[1]:
        raise ValueError("ELS_PROFILE_MISMATCH")
    if not any(i.selection == candidate.request.selection for i in metadata.elsImports):
        raise ValueError("ELS_SELECTION_MISMATCH")
    raw = draft.model_dump(by_alias=True)
    if not set(targets) <= {a.assetNodeId for a in draft.assets}:
        raise ValueError("ELS_TARGET_ASSET_MISSING")
    wps, tools = _scoped(candidate, targets)
    imports = {i.importEntryId: i for i in metadata.elsImports}
    for evidence in imports.values():
        if not evidence.decisions or evidence.decisions.templateId != "freeform-milling-v1":
            raise ValueError("ELS_TEMPLATE_DECISION_REQUIRED")
    for wp in wps:
        evidence = imports[wp.importEntryId]
        source = {r.rowId: r for r in evidence.sourceRows}
        groups = group_source_tools([source[i] for i in evidence.selection.orderedRowIds],
                                   confirmations={i.rowId: i for i in evidence.decisions.identityChoices})
        group_by_row = {r: g["toolTag"] for g in groups for r in g["rowIds"]}
        used = {}
        project = next(a for a in draft.assets if a.assetNodeId == draft.projectAssetNodeId)
        actual = {r.node for r in draft.nodes[project.elementNodeId].fields.get("its_workpieces", [])}
        for step in wp.steps:
            node = raw["nodes"][step.stepNodeId]
            op = operation_for(raw, step.stepNodeId)
            feature = raw["nodes"].get(node["fields"].get("its_feature", {}).get("$node"), {})
            if op["typeId"] != "FreeformOperation" or feature.get("typeId") != "ToolpathFeature":
                raise ValueError("ELS_TEMPLATE_UNSUPPORTED")
            piece_id = feature["fields"].get("its_workpiece", {}).get("$node")
            if piece_id not in actual or raw["nodes"].get(piece_id, {}).get("typeId") != "Workpiece":
                raise ValueError("ELS_PROJECT_WORKPIECE_REQUIRED")
            link = next(l for l in metadata.elsToolLinks if l.stepNodeId == step.stepNodeId)
            if step.kind == "els" and group_by_row[step.sourceRowId] != link.toolTag:
                raise ValueError("ELS_TOOL_SOURCE_MISMATCH")
            if link.assetNodeId in used and used[link.assetNodeId] != link.toolTag:
                raise ValueError("ELS_TOOL_TAG_CONFLICT")
            used[link.assetNodeId] = link.toolTag
            if any(l.assetNodeId == link.assetNodeId for l in draft.toolLinks + draft.manualToolLinks):
                raise ValueError("ELS_TOOL_MODE_CONFLICT")
            if any(l.assetNodeId == link.assetNodeId and l.workplanNodeId != wp.workplanNodeId for l in metadata.elsToolLinks):
                raise ValueError("ELS_TOOL_WORKPLAN_CONFLICT")
            sync_tool(raw, step.stepNodeId, link.assetNodeId, verify=True)
            internal = raw["nodes"][op["fields"]["its_tool"]["$node"]]
            values = values_for(raw, link.assetNodeId)
            for prop in manual_profile()["properties"]:
                field = prop["field"]
                target = internal
                if "." in field:
                    parent, field = field.split(".")
                    refs = internal["fields"].get(parent, [])
                    target = raw["nodes"].get(refs[0].get("$node"), {}) if refs else {}
                if field in target.get("fields", {}) and prop["name"] not in values:
                    raise ValueError("ELS_TOOL_UNSYNCED_PROPERTY")
    for asset_id in tools:
        _identity(raw, asset_id)
        definition = next(t for t in draft.manualTools if t.assetNodeId == asset_id)
        if definition.toolTypeId != "MillingCuttingTool" or definition.legacyUnits:
            raise ValueError("ELS_TOOL_TEMPLATE_UNSUPPORTED")
        if not {"assembly_length", "effective_cutting_diameter", "maximum_depth_of_cut"} <= values_for(raw, asset_id).keys():
            raise ValueError("ELS_TOOL_REQUIRED_PROPERTIES")
    for link in metadata.elsFileLinks:
        if link.assetNodeId not in targets and draft.projectAssetNodeId not in targets:
            continue
        asset, _ = _identity(raw, link.assetNodeId)
        fields = raw["nodes"][asset["elementNodeId"]]["fields"]
        if "reference" in fields or fields.get("path") != link.sourcePath:
            raise ValueError("ELS_RAW_FILE_REFERENCE_OR_PATH")
        wp = next((w for w in metadata.elsWorkplans if w.workplanNodeId == link.workplanNodeId), None)
        if wp is None or wp.importEntryId != link.importEntryId:
            raise ValueError("ELS_FILE_OWNERSHIP")
    return raw


def snapshot_hash(candidate, wp_id):
    """State consistency, NOT source authentication. No session or review self-hashing."""
    draft = candidate.draft.model_dump(by_alias=True)
    metadata = candidate.metadata
    wp = next(w for w in metadata.elsWorkplans if w.workplanNodeId == wp_id)
    links = [l for l in metadata.elsToolLinks if l.workplanNodeId == wp_id]
    tool_ids = {l.assetNodeId for l in links}
    files = [l for l in metadata.elsFileLinks if l.workplanNodeId == wp_id]
    roots = [wp_id, *tool_ids, *(l.assetNodeId for l in files)]
    reachable = reachable_nodes(draft["nodes"], roots)
    refs = [r for r in draft["referenceLinks"] if r["sourceNodeId"] in reachable]
    reachable |= reachable_nodes(draft["nodes"], [r["targetAssetNodeId"] for r in refs])
    project = next(a for a in draft["assets"] if a["assetNodeId"] == draft["projectAssetNodeId"])
    body = dict(profileHash=load_profile()[1], schemaHash=draft["schemaHash"], rulesVersion=draft["rulesVersion"],
        referencePolicyHash=draft["referencePolicyHash"], manualProfileHash=manual_profile()["hash"],
        workplan=wp.model_dump(), links=[l.model_dump() for l in links],
        source=next(i.model_dump() for i in metadata.elsImports if i.importEntryId == wp.importEntryId),
        nodes={i: draft["nodes"][i] for i in sorted(reachable)},
        projectIdentity={k: v for k, v in draft["nodes"][project["assetNodeId"]]["fields"].items() if k != "dt_elements"},
        projectElementIdentity=draft["nodes"][project["elementNodeId"]]["fields"].get("element_id"),
        assets=[a for a in draft["assets"] if a["assetNodeId"] in reachable], references=refs,
        tools=[d for d in draft["manualTools"] if d["assetNodeId"] in tool_ids], files=[l.model_dump() for l in files],
        origins=[o.model_dump(by_alias=True) for o in metadata.elsOrigins if o.nodeId in reachable],
        completion=[e for e in draft["completionEntries"] if e["nodeId"] in reachable])
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _resolver(candidate, require_confirmation):
    def resolve(original, target_ids, *, allow_unstored_files=False):
        _check(candidate, target_ids)
        wps, _ = _scoped(candidate, target_ids)
        if require_confirmation:
            for wp in wps:
                reviews = [r for r in candidate.metadata.elsReviews if r.workplanNodeId == wp.workplanNodeId]
                if len(reviews) != 1 or reviews[0].snapshotHash != snapshot_hash(candidate, wp.workplanNodeId):
                    raise ValueError("ELS_CONFIRMATION_REQUIRED")
        resolved, allowed, issues = resolve_references(original, target_ids, allow_unstored_files=allow_unstored_files)
        raw = resolved.model_dump(by_alias=True)
        nodes = raw["nodes"]
        for wp in wps:
            for link in (l for l in candidate.metadata.elsToolLinks if l.workplanNodeId == wp.workplanNodeId):
                op = operation_for(raw, link.stepNodeId)
                asset, path = _identity(raw, link.assetNodeId)
                policy = next((p for p in get_profile().referencePolicies if p.targetRole == "tool" and policy_for(op["typeId"], p.fieldName) == p), None)
                if not policy or policy.fieldName in op["fields"]:
                    raise ValueError("ELS_RAW_MANAGED_REFERENCE")
                op["fields"][policy.fieldName] = add_node(raw, get_profile().referenceType,
                    element_id=f"tool-ref-{op['nodeId']}", category="reference",
                    keys=[add_node(raw, get_profile().keyValueType, key=policy.key, value=path)])
                allowed.add((op["nodeId"], policy.fieldName))
        for link in candidate.metadata.elsFileLinks:
            if link.assetNodeId not in target_ids:
                continue
            asset, _ = _identity(raw, link.assetNodeId)
            project, _ = _identity(raw, link.projectAssetNodeId)
            root = nodes[link.projectAssetNodeId]["fields"]
            keys = dict(DT_GLOBAL_ASSET=root["asset_global_id"], DT_ASSET=root["id"],
                        DT_PROJECT=nodes[project["elementNodeId"]]["fields"]["element_id"],
                        WORKPLAN=nodes[link.workplanNodeId]["fields"]["its_id"])
            nodes[asset["elementNodeId"]]["fields"]["reference"] = [add_node(raw, get_profile().referenceType,
                element_id="els-file-project-ref", category="reference",
                keys=[add_node(raw, get_profile().keyValueType, key=k, value=v) for k, v in keys.items()])]
            issues.append(dict(nodeId=asset["elementNodeId"], fieldName="value", itemId=None, code="FILE_STORAGE_PENDING",
                severity="warning", sourceFileAvailable=False, message="ELS file metadata only; original bytes are unavailable. dt_file.value is omitted."))
        return CreatorDraft.model_validate(raw), allowed, issues
    return resolve


def review(candidate, targets, *, require_confirmation=True):
    check_request_budget(dict(candidate=candidate.model_dump(by_alias=True), targetAssetNodeIds=targets))
    try:
        result = preview_assets(candidate.draft, targets, reference_resolver=_resolver(candidate, require_confirmation))
    except (ValueError, KeyError, TypeError, StopIteration) as exc:
        code = str(exc) if isinstance(exc, ValueError) and str(exc).startswith("ELS_") else "ELS_GRAPH_INVALID"
        return dict(valid=False, finalizable=False, machineReady=False, persisted=False, artifacts=[], warnings=[],
                    issues=[dict(code=code, severity="error", nodeId=None, fieldName=None, itemId=None, message=code)])
    raw = candidate.draft.model_dump(by_alias=True)
    reachable = reachable_nodes(raw["nodes"], targets)
    for origin in candidate.metadata.elsOrigins:
        if origin.nodeId not in reachable or origin.fieldName not in candidate.draft.nodes[origin.nodeId].fields:
            continue
        changed = candidate.draft.nodes[origin.nodeId].fields[origin.fieldName] != origin.appliedValue
        if origin.kind in {"placeholder", "default"} or changed:
            result["warnings"].append(dict(nodeId=origin.nodeId, fieldName=origin.fieldName, itemId=None,
                code="ELS_" + ("EDITED_SOURCE" if changed else origin.kind.upper()), severity="warning", message=origin.reason,
                changed=changed, kind=origin.kind))
    result.update(persisted=False, purpose="authoring-review-only", sourceAuthentication=False)
    row_ids = {s.rowId for o in candidate.metadata.elsOrigins if o.nodeId in reachable for s in o.sources}
    if candidate.draft.projectAssetNodeId in targets:
        row_ids.update(r for i in candidate.metadata.elsImports for r in i.selection.orderedRowIds)
    rules = {r.id: r for r in load_profile()[0].numericRules}
    for evidence in candidate.metadata.elsImports:
        rows = {r.rowId: r for r in evidence.sourceRows}
        for choice in evidence.decisions.valueChoices if evidence.decisions else []:
            if choice.rowId not in row_ids:
                continue
            if choice.ruleId not in rules or choice.rowId not in rows:
                raise ValueError("ELS_VALUE_CHOICE_SCOPE")
            mapped = numeric_candidate(rules[choice.ruleId], rows[choice.rowId].values, column=choice.column, reason=choice.reason)
            if mapped.get("unrepresentedColumns"):
                result["warnings"].append(dict(nodeId=None, fieldName=None, itemId=None, code="ELS_UNREPRESENTED_CONDITIONS",
                    severity="warning", message=choice.reason, sourceRowId=choice.rowId, columns=mapped["unrepresentedColumns"]))
    result["elsReport"] = dict(sourceAuthentication=False, scope="selected-authoring-assets",
        imports=[dict(importEntryId=i.importEntryId, sourceSha256=i.sourceSha256, selection=i.selection.model_dump(),
                      decisions=i.decisions.model_dump() if i.decisions else None) for i in candidate.metadata.elsImports],
        origins=[o.model_dump(by_alias=True) for o in candidate.metadata.elsOrigins if o.nodeId in reachable])
    result["warnings"].append(dict(nodeId=None, fieldName=None, itemId=None, code="ELS_AUTHORING_ONLY", severity="warning",
        message="ELS source/authoring review only. NC execution, collision and machining safety have not been verified."))
    return result


def confirm(request):
    check_request_budget(request.model_dump(by_alias=True))
    candidate = request.candidate.model_copy(deep=True)
    if not request.acknowledged:
        raise ValueError("ELS_ACKNOWLEDGEMENT_REQUIRED")
    wp_ids = request.workplanNodeIds
    if len(set(wp_ids)) != len(wp_ids) or set(wp_ids) != {w.workplanNodeId for w in candidate.metadata.elsWorkplans}:
        raise ValueError("ELS_CONFIRM_SCOPE")
    # Check completeness without requiring an existing confirmation; no circular workflow.
    for asset in candidate.draft.assets:
        result = review(candidate, [asset.assetNodeId], require_confirmation=False)
        if not result["valid"]:
            raise ValueError("ELS_CONFIRM_VALIDATION_FAILED:" + result["issues"][0]["code"])
    candidate.metadata.elsReviews = [ElsReview(workplanNodeId=wp, snapshotHash=snapshot_hash(candidate, wp),
        profileHash=load_profile()[1], acknowledged=True) for wp in wp_ids]
    return candidate
