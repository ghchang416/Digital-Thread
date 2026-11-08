"""ELS source -> staged DT graph. No mutation of the caller's workspace or database."""
from decimal import Decimal, InvalidOperation
import math
from urllib.parse import urlsplit
from uuid import uuid4

from src.schemas.creator import CreatorDraft
from src.schemas.creator_completion import CompletionRequest
from src.schemas.creator_els import ElsCandidate, ElsImport, ElsMetadata, ElsSourceRow
from src.schemas.creator_manual import ManualToolRequest, ToolInput
from src.services.creator.catalog import get_catalog
from src.services.creator.completion import complete_workplan
from src.services.creator.manual import add_node, manual_profile, prepare_tool, sync_tool
from src.services.creator.schema_provider import get_profile, policy_hash
from .contracts import check_request_budget, validate_application
from .profile import load_profile, numeric_candidate
from .selection import cells, value
from .tool_identity import group_source_tools


def _selected(context, request):
    selection = request.request.selection
    expected = (value(context["part"], "Part_No"), value(context["part"], "Part_Rev"),
                value(context["operation"], "Op_No"), context["programNo"], context["programRevision"])
    if expected != (selection.partNo, selection.partRevision, selection.opNo, selection.programNo, selection.programRevision):
        raise ValueError("ELS_SELECTION_SCOPE")
    source_type = value(context["operation"], "공정 Type")
    if isinstance(source_type, str) and any(word in source_type.casefold() for word in ("turn", "선반", "터닝")):
        raise ValueError("ELS_TURNING_NOT_SUPPORTED")
    rows = {r["rowId"]: r for r in context["rows"]}
    chosen = selection.orderedRowIds
    if set(chosen + [r.rowId for r in selection.excludedRows]) != set(rows):
        raise ValueError("ELS_EXCLUSION_REASON_REQUIRED")
    if any(i["code"] in {"DUPLICATE_SOURCE_KEY", "SOURCE_ROW_KEY_MISSING"} for r in chosen for i in rows[r]["issues"]):
        raise ValueError("ELS_AMBIGUOUS_SOURCE_ROW")
    changed_order = chosen != [r["rowId"] for r in context["rows"] if r["rowId"] in chosen]
    bad_sequence = any(i["code"] in {"SEQ_CONFLICT", "INVALID_SEQUENCE"} for r in chosen for i in rows[r]["issues"])
    for row_id in chosen:
        try:
            raw = value(rows[row_id], "SEQNO")
            if isinstance(raw, bool) or raw is None or not Decimal(str(raw)).is_finite() or Decimal(str(raw)) < 0:
                bad_sequence = True
        except InvalidOperation:
            bad_sequence = True
    if (changed_order or bad_sequence) and not selection.orderReason:
        raise ValueError("ELS_ORDER_CONFIRMATION_REQUIRED")
    if set(c.rowId for c in request.decisions.valueChoices + request.decisions.identityChoices) - set(chosen):
        raise ValueError("ELS_CHOICE_SCOPE")
    return [ElsSourceRow(rowId=r, table="Operation_Machining", values=rows[r]["values"]) for r in chosen]


class Builder:
    def __init__(self, draft, import_id):
        self.draft, self.import_id, self.origins = draft, import_id, {}

    def record(self, node_id, field, kind="generated", *, sources=None, reason="Generated authoring structure.", rule="els-vertical-1", **units):
        self.origins[node_id, field] = dict(importEntryId=self.import_id, nodeId=node_id, fieldName=field, kind=kind,
            sources=sources or [], appliedValue=self.draft["nodes"][node_id]["fields"][field], rule=rule, reason=reason, **units)

    def put(self, node_id, field, value, kind="generated", **origin):
        self.draft["nodes"][node_id]["fields"][field] = value
        self.record(node_id, field, kind, **origin)

    def node(self, type_id, **fields):
        ref = add_node(self.draft, type_id, **fields)
        for field in fields:
            self.record(ref["$node"], field)
        return ref

    def asset(self, role, **fields):
        element = self.node(get_profile().assetTypes[role], element_id=f"{role}_{uuid4().hex[:12]}", **fields)
        global_id = self.draft["nodes"][self.draft["projectAssetNodeId"]]["fields"]["asset_global_id"]
        root = self.node("DtAsset", asset_global_id=global_id, id=f"{role}_{uuid4().hex[:12]}", schema_version="v31",
                         asset_kind="instance", dt_elements=[element])
        asset = dict(assetNodeId=root["$node"], elementNodeId=element["$node"], role=role)
        self.draft["assets"].append(asset)
        return asset

    def reference(self, source, role, target):
        node_type = self.draft["nodes"][source]["typeId"]
        policies = [p for p in get_profile().referencePolicies if p.sourceType == node_type and p.targetRole == role and p.editor == "asset-picker"]
        if len(policies) != 1:
            raise ValueError("ELS_REFERENCE_POLICY_UNSUPPORTED")
        self.draft["referenceLinks"].append(dict(sourceNodeId=source, policyId=policies[0].id, targetAssetNodeId=target))

    def mapped(self, target, field, row, column):
        key, raw = cells(row["values"]).get(column.casefold(), (None, None))
        if raw is None or raw == "":
            return False
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("ELS_INVALID_SOURCE_TEXT")
        self.put(target, field, raw, "source", sources=[dict(rowId=row["rowId"], column=key)], reason="Selected source value.")
        return True

    def capture_added(self, previous):
        for key, node in self.draft["nodes"].items():
            for name, val in node["fields"].items():
                if key not in previous or name not in previous[key]["fields"]:
                    self.record(key, name)


def prepare(context, request):
    check_request_budget(request.model_dump(by_alias=True))
    profile, profile_hash = load_profile()
    base, command = request.baseDraft, request.request
    catalog = get_catalog()
    if (command.baseDraftId, command.baseRevision) != (base.draftId, base.revision):
        raise ValueError("ELS_STALE_BASE")
    if command.profileHash != profile_hash or any(getattr(base, k) != catalog[k] for k in ("schemaHash", "schemaVersion", "rulesVersion")):
        raise ValueError("ELS_SCHEMA_OR_PROFILE_MISMATCH")
    chosen = _selected(context, request)
    groups = group_source_tools(chosen, confirmations={i.rowId: i for i in request.decisions.identityChoices})
    if set(t.toolTag for t in request.decisions.toolValues) - {g["toolTag"] for g in groups}:
        raise ValueError("ELS_TOOL_VALUE_SCOPE")
    numeric_rules = {r.id: r for r in profile.numericRules}
    if set(c.ruleId for c in request.decisions.valueChoices) - set(numeric_rules):
        raise ValueError("ELS_UNKNOWN_VALUE_RULE")
    choices = {(c.rowId, c.ruleId): c for c in request.decisions.valueChoices}
    candidates = {}
    for row in chosen:
        for rule in profile.numericRules:
            choice = choices.get((row.rowId, rule.id))
            result = numeric_candidate(rule, row.values, column=choice.column if choice else None, reason=choice.reason if choice else None)
            if result["status"] in {"invalid", "selection-required"}:
                raise ValueError(f"ELS_VALUE_CHOICE_REQUIRED:{row.rowId}:{rule.id}")
            if result["status"] == "candidate" and not math.isfinite(float(result["value"])):
                raise ValueError("ELS_NUMERIC_RANGE")
            candidates[row.rowId, rule.id] = result
    files = {r["rowId"]: r for r in context["files"]}
    if set(c.rowId for c in request.decisions.fileChoices) - files.keys():
        raise ValueError("ELS_FILE_SELECTION_SCOPE")
    if command.mode == "append-tools" and request.decisions.fileChoices:
        raise ValueError("ELS_APPEND_TOOLS_ONLY")
    source_rows = [ElsSourceRow(rowId=r["rowId"], table="Operation_Machining", values=r["values"]) for r in context["rows"]]
    source_rows += [ElsSourceRow(**context["part"]), ElsSourceRow(**context["operation"])]
    if request.includeMachine and command.mode == "replace-project":
        if len(context["machines"]) != 1:
            raise ValueError("ELS_MACHINE_MATCH_REQUIRED")
        source_rows.append(ElsSourceRow(**context["machines"][0]))
    source_rows += [ElsSourceRow(**files[c.rowId]) for c in request.decisions.fileChoices]
    evidence = ElsImport(importEntryId=uuid4().hex, sourceSha256=context["sourceSha256"], sourceName=context["sourceName"],
        readerVersion=context["readerVersion"], sourceSchemaHash=context["sourceSchemaHash"], profileHash=profile_hash,
        selection=command.selection, sourceRows=source_rows, decisions=request.decisions)
    if command.mode == "replace-project":
        uri = urlsplit(request.globalAssetBaseUri)
        if uri.scheme not in {"http", "https"} or not uri.netloc or uri.query or uri.fragment or uri.username or uri.password or any(c.isspace() for c in request.globalAssetBaseUri):
            raise ValueError("ELS_INVALID_GLOBAL_ASSET_BASE")
        draft_id, root_id = uuid4().hex, uuid4().hex
        draft = CreatorDraft(schemaHash=catalog["schemaHash"], rulesVersion=catalog["rulesVersion"], draftId=draft_id,
            revision=0, nodes={}, assets=[], projectAssetNodeId=root_id, referencePolicyHash=policy_hash()).model_dump(by_alias=True)
        draft["nodes"][root_id] = dict(nodeId=root_id, typeId="DtAsset", fields=dict(schema_version="v31", asset_kind="instance",
            asset_global_id=request.globalAssetBaseUri.rstrip("/") + "/" + draft_id, id="project"))
    else:
        draft = base.model_dump(by_alias=True)
    builder = Builder(draft, evidence.importEntryId)
    metadata = ElsMetadata(elsImports=[evidence]).model_dump(by_alias=True)
    wp_id = workpiece_id = None
    if command.mode == "replace-project":
        for field in draft["nodes"][root_id]["fields"]:
            builder.record(root_id, field)
        workpiece_id = builder.node("Workpiece", its_id=command.selection.partNo)["$node"]
        wp_id = builder.node("Workplan", its_id=f"OP_{command.selection.opNo}_PGM_{command.selection.programNo}_{command.selection.programRevision}", its_elements=[])["$node"]
        main = builder.node("Workplan", its_id="main_workplan", its_elements=[{"$node": wp_id}])
        project = builder.node("DtProject", element_id="project", its_id=request.projectName.strip(), display_name=request.projectName.strip(),
                               main_workplan=main, its_workpieces=[{"$node": workpiece_id}])
        builder.put(root_id, "dt_elements", [project])
        draft["assets"].append(dict(assetNodeId=root_id, elementNodeId=project["$node"], role="project"))
        builder.mapped(workpiece_id, "its_id", context["part"], "Part_No")
        if request.includeMaterial:
            material = builder.asset("material", category="Material")
            for target, column in (("standard_identifier", "Spec_재질"), ("material_identifier", "Part_Material")):
                if not builder.mapped(material["elementNodeId"], target, context["part"], column) and command.includePlaceholders:
                    default = next(d for d in profile.defaults if d.typeId == "Material" and d.field == target)
                    builder.put(material["elementNodeId"], target, default.value, default.kind, reason=default.reason)
            builder.reference(workpiece_id, "material", material["assetNodeId"])
        if request.includeMachine:
            machine = builder.asset("machine", category="MachineTool")
            machine_node = builder.node("MachineTool")["$node"]
            builder.put(machine["elementNodeId"], "machine_tool", {"$node": machine_node})
            if not builder.mapped(machine_node, "description", context["machines"][0], "설비명") and command.includePlaceholders:
                default = next(d for d in profile.defaults if d.typeId == "MachineTool" and d.field == "description")
                builder.put(machine_node, "description", default.value, default.kind, reason=default.reason)
            builder.reference(wp_id, "machine", machine["assetNodeId"])
    row_lookup = {row.rowId: row for row in chosen}
    tool_assets, tool_origins = {}, {}
    props = {p["name"]: p for p in manual_profile()["properties"]}
    for group in groups:
        values, origins = {}, {}
        for rule_id, prop_name in (("diameter", "effective_cutting_diameter"), ("corner-radius", "corner_radius")):
            mapped = [candidates[r, rule_id] for r in group["rowIds"]]
            distinct = {m["value"] for m in mapped if m["status"] == "candidate"}
            if len(distinct) > 1:
                raise ValueError("ELS_TOOL_CONFIGURATION_CONFLICT")
            if distinct:
                raw = next(iter(distinct))
                values[prop_name] = ToolInput(value=float(raw), unit="mm")
                sources = [dict(rowId=r, column=cells(row_lookup[r].values)[name.casefold()][0])
                           for r, m in zip(group["rowIds"], mapped) for name in m.get("columns", [])]
                origins[prop_name] = dict(kind="source", sources=sources[:16], reason="Explicit source tool dimension selection.", rule=rule_id, sourceUnit="mm", targetUnit="mm")
        manual = next((t for t in request.decisions.toolValues if t.toolTag == group["toolTag"]), None)
        if manual:
            for name, item in manual.values.items():
                if name in values:
                    raise ValueError("ELS_SOURCE_VALUE_ALREADY_SELECTED")
                values[name] = item
                origins[name] = dict(kind="manual", reason=manual.reason)
        for default in (d for d in profile.defaults if d.typeId == "MillingCuttingTool"):
            prop_name = next(p["name"] for p in props.values() if p["field"] == default.field)
            if prop_name not in values and command.includePlaceholders:
                values[prop_name] = ToolInput(value=default.value, unit=props[prop_name]["unit"])
                origins[prop_name] = dict(kind=default.kind, reason=default.reason)
        previous = dict(draft["nodes"])
        result = prepare_tool(ManualToolRequest(draft=CreatorDraft.model_validate(draft), expectedRevision=draft["revision"],
            profileHash=manual_profile()["hash"], name=group["toolTag"], toolTypeId="MillingCuttingTool", values=values))
        draft = result["draft"]
        builder.draft = draft
        builder.capture_added(previous)
        asset = next(a for a in draft["assets"] if a["assetNodeId"] == result["assetNodeId"])
        builder.put(asset["elementNodeId"], "element_id", group["toolTag"])
        tool_assets[group["toolTag"]] = asset["assetNodeId"]
        tool_origins[asset["assetNodeId"]] = origins
        for ref in draft["nodes"][asset["elementNodeId"]]["fields"].get("numerical_value", []):
            node = draft["nodes"][ref["$node"]]
            builder.record(node["nodeId"], "value_component", **origins[node["fields"]["value_name"]])
    if wp_id:
        owned_steps = []
        for ordinal, row in enumerate(chosen, 1):
            op = builder.node("FreeformOperation", its_id=f"operation_{ordinal}")
            feature = builder.node("ToolpathFeature", its_id=f"feature_{ordinal}", its_workpiece={"$node": workpiece_id})
            step = builder.node("MachiningWorkingstep", its_id=f"step_{ordinal}", its_operation=op, its_feature=feature)["$node"]
            builder.mapped(step, "its_id", dict(rowId=row.rowId, values=row.values), "DESC")
            if value(dict(values=row.values), "DESC") not in (None, ""):
                origin = builder.origins[step, "its_id"]
                builder.put(step, "its_id", f"{ordinal}_{draft['nodes'][step]['fields']['its_id']}", "derived",
                            sources=origin["sources"], reason="Source description with a unique selected-order prefix.")
            technology = builder.node("MillingTechnology")["$node"]
            builder.put(op["$node"], "its_technology", {"$node": technology})
            for rule_id in ("spindle", "feedrate"):
                candidate = candidates[row.rowId, rule_id]
                if candidate["status"] == "candidate":
                    builder.put(technology, numeric_rules[rule_id].targetField, float(candidate["value"]), "derived",
                        sources=[dict(rowId=row.rowId, column=cells(row.values)[name.casefold()][0]) for name in candidate["columns"]],
                        reason=candidate.get("reason") or "Source unit conversion.", rule=rule_id,
                        sourceUnit=candidate["sourceUnit"], targetUnit=candidate["targetUnit"])
            for default in (d for d in profile.defaults if d.typeId == "MillingTechnology"):
                builder.put(technology, default.field, default.value, default.kind, reason=default.reason)
            group = next(g for g in groups if row.rowId in g["rowIds"])
            asset_id = tool_assets[group["toolTag"]]
            previous = dict(draft["nodes"])
            sync_tool(draft, step, asset_id)
            builder.capture_added(previous)
            builder.record(op["$node"], "its_tool")
            tool_id = draft["nodes"][op["$node"]]["fields"]["its_tool"]["$node"]
            for name, origin in tool_origins[asset_id].items():
                target, field = tool_id, props[name]["field"]
                if "." in field:
                    parent, field = field.split(".")
                    target = draft["nodes"][tool_id]["fields"][parent][0]["$node"]
                builder.record(target, field, **origin)
            draft["nodes"][wp_id]["fields"]["its_elements"].append({"$node": step})
            owned_steps.append(dict(kind="els", stepNodeId=step, sourceRowId=row.rowId))
            metadata["elsToolLinks"].append(dict(workplanNodeId=wp_id, stepNodeId=step, assetNodeId=asset_id,
                toolTag=group["toolTag"], sourceToolNo=value(dict(values=row.values), "TOOLNO")))
        builder.record(wp_id, "its_elements")
        metadata["elsWorkplans"] = [dict(workplanNodeId=wp_id, importEntryId=evidence.importEntryId, steps=owned_steps)]
        for choice in request.decisions.fileChoices:
            source = files[choice.rowId]
            path = value(source, "File_Path")
            if not isinstance(path, str) or not path.strip() or any(ord(c) < 32 for c in path):
                raise ValueError("ELS_INVALID_FILE_PATH")
            file = builder.asset("file", category=choice.purpose, content_type="application/octet-stream")
            builder.put(file["elementNodeId"], "content_type", "application/octet-stream", "default", reason="Source bytes unavailable; media type is unverified.")
            builder.mapped(file["elementNodeId"], "path", source, "File_Path")
            metadata["elsFileLinks"].append(dict(assetNodeId=file["assetNodeId"], projectAssetNodeId=draft["projectAssetNodeId"],
                workplanNodeId=wp_id, importEntryId=evidence.importEntryId, sourceRowId=source["rowId"], sourcePath=path, purpose=choice.purpose))
        result = complete_workplan(CompletionRequest(draft=CreatorDraft.model_validate(draft), workplanNodeId=wp_id,
            includePlaceholders=command.includePlaceholders))
        draft = result["draft"]
        builder.draft = draft
        for entry in draft["completionEntries"]:
            builder.record(entry["nodeId"], entry["fieldName"], entry["kind"], rule=entry["rule"], reason=entry["reason"])
    draft["revision"] = 0 if command.mode == "replace-project" else base.revision + 1
    metadata["elsOrigins"] = list(builder.origins.values())
    candidate = ElsCandidate(request=command, draft=draft, metadata=metadata)
    validate_application(candidate, base)
    check_request_budget(dict(candidate=candidate.model_dump(by_alias=True), targetAssetNodeIds=[a.assetNodeId for a in candidate.draft.assets[:10]]))
    return candidate
