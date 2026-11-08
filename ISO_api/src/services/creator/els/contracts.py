"""Candidate preflight only. No reference injection, XML, active draft mutation or I/O."""
import json
import re

from src.schemas.creator import CreatorDraft, NodeRef
from src.schemas.creator_els import ElsCandidate, ElsMetadata, ElsSourceStep, unique
from src.services.creator.catalog import get_catalog
from .profile import load_profile
from .reader import normalized_name


def json_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def check_request_budget(*envelopes):
    limits = load_profile()[0].limits
    if any(json_bytes(envelope) > limits.maxRequestBytes for envelope in envelopes):
        raise ValueError("ELS_REQUEST_BUDGET")


def graph_budget(draft, limits):
    reachable = {}
    for asset in draft.assets:
        reachable[asset.assetNodeId] = set()
        visits = 0
        stack = [(asset.assetNodeId, ())]
        while stack:
            node_id, ancestors = stack.pop()
            visits += 1
            if visits > limits.maxExpansion:
                raise ValueError("ELS_EXPANSION_LIMIT")
            if node_id in ancestors:
                raise ValueError("ELS_CYCLIC_GRAPH")
            if len(ancestors) >= limits.maxDepth:
                raise ValueError("ELS_DEPTH_LIMIT")
            node = draft.nodes.get(node_id)
            if not node:
                raise ValueError("ELS_MISSING_NODE")
            reachable[asset.assetNodeId].add(node_id)
            for value in node.fields.values():
                for item in value if isinstance(value, list) else [value]:
                    if isinstance(item, NodeRef):
                        stack.append((item.node, ancestors + (node_id,)))
    return reachable


def validate_candidate_metadata(draft: CreatorDraft, metadata: ElsMetadata):
    profile, profile_hash = load_profile()
    catalog = get_catalog()
    if draft.schemaHash != catalog["schemaHash"] or draft.rulesVersion != catalog["rulesVersion"] or draft.schemaVersion != profile.schemaVersion:
        raise ValueError("ELS_SCHEMA_MISMATCH")
    merged = {**draft.model_dump(by_alias=True), **metadata.model_dump(by_alias=True)}
    if json_bytes(merged) > profile.limits.maxDraftBytes:
        raise ValueError("ELS_DRAFT_BUDGET")
    reachable = graph_budget(draft, profile.limits)
    imports = {item.importEntryId: item for item in metadata.elsImports}
    unique([i.importEntryId for i in metadata.elsImports], "ELS import")
    unique([wp.workplanNodeId for wp in metadata.elsWorkplans], "ELS workplan")
    unique([link.stepNodeId for link in metadata.elsToolLinks], "ELS step tool")
    unique([link.assetNodeId for link in metadata.elsFileLinks], "ELS file")
    unique([r.workplanNodeId for r in metadata.elsReviews], "ELS review")
    if any(item.profileHash != profile_hash for item in metadata.elsImports):
        raise ValueError("ELS_PROFILE_MISMATCH")
    rows = {key: {row.rowId: row for row in item.sourceRows} for key, item in imports.items()}
    assets = {asset.assetNodeId: asset for asset in draft.assets}
    tool_definitions = {tool.assetNodeId: tool for tool in draft.manualTools}
    unique([tool.assetNodeId for tool in draft.manualTools], "tool definition")
    legacy_wps = set(draft.manualWorkplans) | {l.workplanNodeId for l in draft.toolLinks + draft.manualToolLinks} | {r.workplanNodeId for r in draft.ncReviews}
    legacy_steps = {l.stepNodeId for l in draft.manualToolLinks} | {s for link in draft.toolLinks for s in link.stepNodeIds}
    owned_steps, workplans = {}, {}
    for wp in metadata.elsWorkplans:
        if wp.importEntryId not in imports:
            raise ValueError("ELS_MISSING_IMPORT")
        if wp.workplanNodeId in legacy_wps:
            raise ValueError("ELS_WORKPLAN_MODE_CONFLICT")
        if wp.workplanNodeId not in reachable.get(draft.projectAssetNodeId, set()):
            raise ValueError("ELS_WORKPLAN_NOT_IN_PROJECT")
        node = draft.nodes.get(wp.workplanNodeId)
        if not node or node.typeId != "Workplan":
            raise ValueError("ELS_INVALID_WORKPLAN")
        direct = node.fields.get("its_elements", [])
        if not isinstance(direct, list) or not all(isinstance(ref, NodeRef) for ref in direct):
            raise ValueError("ELS_INVALID_ELEMENTS")
        step_ids = [s.stepNodeId for s in wp.steps]
        unique(step_ids, "ELS step")
        # Initial vertical profile permits one program WP of machining steps, not mixed CAM/ELS ownership.
        if [ref.node for ref in direct] != step_ids:
            raise ValueError("ELS_STEP_ORDER_MISMATCH")
        if [s.sourceRowId for s in wp.steps if isinstance(s, ElsSourceStep)] != imports[wp.importEntryId].selection.orderedRowIds:
            raise ValueError("ELS_SOURCE_ORDER_MISMATCH")
        for step in wp.steps:
            if step.stepNodeId in owned_steps or step.stepNodeId in legacy_steps or draft.nodes.get(step.stepNodeId) is None or draft.nodes[step.stepNodeId].typeId != "MachiningWorkingstep":
                raise ValueError("ELS_STEP_OWNERSHIP")
            owned_steps[step.stepNodeId] = wp.workplanNodeId
        workplans[wp.workplanNodeId] = wp
    linked = set()
    tags = {}
    for link in metadata.elsToolLinks:
        asset = assets.get(link.assetNodeId)
        if owned_steps.get(link.stepNodeId) != link.workplanNodeId:
            raise ValueError("ELS_TOOL_OWNERSHIP")
        wp = workplans[link.workplanNodeId]
        step = next(s for s in wp.steps if s.stepNodeId == link.stepNodeId)
        if isinstance(step, ElsSourceStep):
            raw = {normalized_name(k): v for k, v in rows[wp.importEntryId][step.sourceRowId].values.items()}.get("toolno")
            if raw != link.sourceToolNo or not isinstance(raw, str) or not re.fullmatch(r"[Tt]?[0-9]{1,6}", raw) or int(raw.lstrip("Tt")) != int(link.toolTag[1:]):
                raise ValueError("ELS_TOOL_SOURCE_MISMATCH")
        elif link.sourceToolNo is not None:
            raise ValueError("ELS_MANUAL_STEP_HAS_SOURCE_TOOL")
        operation = draft.nodes[link.stepNodeId].fields.get("its_operation")
        operation_node = draft.nodes.get(operation.node) if isinstance(operation, NodeRef) else None
        if operation_node and "ref_dt_cutting_tool" in operation_node.fields:
            raise ValueError("ELS_RAW_MANAGED_REFERENCE")
        if not asset or asset.role != "tool" or asset.elementNodeId not in draft.nodes or draft.nodes[asset.elementNodeId].typeId != "DtCuttingTool13399" or link.assetNodeId not in tool_definitions:
            raise ValueError("ELS_TOOL_DEFINITION")
        tag = (link.workplanNodeId, int(link.toolTag[1:]))
        if tag in tags and tags[tag] != link.assetNodeId:
            raise ValueError("ELS_TOOL_TAG_CONFLICT")
        tags[tag] = link.assetNodeId
        linked.add(link.stepNodeId)
    if linked != set(owned_steps):
        raise ValueError("ELS_MISSING_TOOL_LINK")
    for node in draft.nodes.values():
        elements = node.fields.get("its_elements", [])
        if node.typeId == "Workplan" and isinstance(elements, list):
            for ref in elements:
                if isinstance(ref, NodeRef) and ref.node in owned_steps and node.nodeId != owned_steps[ref.node]:
                    raise ValueError("ELS_STEP_OWNERSHIP")
    for origin in metadata.elsOrigins:
        node = draft.nodes.get(origin.nodeId)
        if origin.importEntryId not in imports or not node or origin.fieldName not in {f["fieldName"] for f in catalog["types"].get(node.typeId, {}).get("fields", [])}:
            raise ValueError("ELS_INVALID_ORIGIN")
        for source in origin.sources:
            row = rows[origin.importEntryId].get(source.rowId)
            if not row or source.column not in row.values:
                raise ValueError("ELS_MISSING_SOURCE_CELL")
    for review in metadata.elsReviews:
        if review.workplanNodeId not in workplans or review.profileHash != profile_hash:
            raise ValueError("ELS_INVALID_REVIEW_SCOPE")
    for link in metadata.elsFileLinks:
        asset = assets.get(link.assetNodeId)
        row = rows.get(link.importEntryId, {}).get(link.sourceRowId)
        if not asset or asset.role != "file" or link.projectAssetNodeId != draft.projectAssetNodeId or (link.workplanNodeId is not None and link.workplanNodeId not in workplans):
            raise ValueError("ELS_FILE_OWNERSHIP")
        if not row or row.table not in {"Part_File", "Machine_File", "Tool_File"} or {normalized_name(k): v for k, v in row.values.items()}.get("file_path") != link.sourcePath:
            raise ValueError("ELS_FILE_SOURCE")
        node = draft.nodes[asset.elementNodeId]
        if node.typeId != "DtFile" or "value" in node.fields or any(f.assetNodeId == link.assetNodeId for f in draft.fileLinks):
            raise ValueError("ELS_FILE_MODE_CONFLICT")
    # This is structural preflight, NOT ELS confirmation or XML validation.
    return {"profileHash": profile_hash, "draftBytes": json_bytes(merged), "confirmationRequired": True, "persisted": False}


def validate_application(candidate: ElsCandidate, base: CreatorDraft, base_metadata: ElsMetadata | None = None):
    """Validate a prepared response against its base, without applying it or touching recovery."""
    request, updated = candidate.request, candidate.draft
    if request.baseDraftId != base.draftId or request.baseRevision != base.revision:
        raise ValueError("ELS_STALE_BASE")
    if request.profileHash != load_profile()[1]:
        raise ValueError("ELS_PROFILE_MISMATCH")
    if not any(item.selection == request.selection for item in candidate.metadata.elsImports):
        raise ValueError("ELS_SELECTION_MISMATCH")
    if request.mode == "append-tools":
        old = base.model_dump(by_alias=True)
        new = updated.model_dump(by_alias=True)
        for field in old.keys() - {"revision", "nodes", "assets", "manualTools"}:
            if old[field] != new[field]:
                raise ValueError("ELS_APPEND_CHANGED_EXISTING_DATA")
        if any(updated.nodes.get(key) != node for key, node in base.nodes.items()):
            raise ValueError("ELS_APPEND_CHANGED_EXISTING_NODE")
        if updated.assets[:len(base.assets)] != base.assets or updated.manualTools[:len(base.manualTools)] != base.manualTools:
            raise ValueError("ELS_APPEND_CHANGED_EXISTING_ASSET")
        added_assets = updated.assets[len(base.assets):]
        added_ids = {a.assetNodeId for a in added_assets}
        definitions = updated.manualTools[len(base.manualTools):]
        if not added_assets or any(a.role != "tool" for a in added_assets) or {t.assetNodeId for t in definitions} != added_ids:
            raise ValueError("ELS_APPEND_TOOLS_ONLY")
        if any(updated.nodes.get(a.elementNodeId) is None or updated.nodes[a.elementNodeId].typeId != "DtCuttingTool13399" for a in added_assets):
            raise ValueError("ELS_APPEND_TOOLS_ONLY")
        previous = base_metadata or ElsMetadata()
        for name in ("elsWorkplans", "elsToolLinks", "elsReviews", "elsFileLinks"):
            if getattr(previous, name) != getattr(candidate.metadata, name):
                raise ValueError("ELS_APPEND_CHANGED_EXISTING_POLICY")
        for name in ("elsImports", "elsOrigins"):
            existing, incoming = getattr(previous, name), getattr(candidate.metadata, name)
            if incoming[:len(existing)] != existing:
                raise ValueError("ELS_APPEND_CHANGED_EXISTING_SOURCE")
        for origin in candidate.metadata.elsOrigins[len(previous.elsOrigins):]:
            if origin.nodeId in base.nodes:
                raise ValueError("ELS_APPEND_CHANGED_EXISTING_SOURCE")
        reach = graph_budget(updated, load_profile()[0].limits)
        new_nodes = set(updated.nodes) - set(base.nodes)
        covered = set().union(*(reach[asset_id] for asset_id in added_ids))
        if not new_nodes <= covered or covered & set(base.nodes):
            raise ValueError("ELS_APPEND_GRAPH_OWNERSHIP")
    return validate_candidate_metadata(updated, candidate.metadata)
