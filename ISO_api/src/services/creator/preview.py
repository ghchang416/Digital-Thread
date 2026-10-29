"""Compile a draft asset using model metadata. This is not final ISO approval."""

from xsdata.formats.dataclass.parsers import XmlParser
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig

from src.schemas.creator import CreatorDraft, NodeRef, ScalarItem
from src.services.creator.catalog import get_catalog, model_classes
from src.services.creator.schema_provider import get_model, get_profile
from src.services.creator.references import resolve_references
from src.services.creator.completion_warnings import completion_warnings


def preview_assets(draft: CreatorDraft, target_ids: list[str]):
    catalog = get_catalog()
    model, profile = get_model(), get_profile()
    issues, artifacts = [], []
    classes = model_classes()
    visits = 0
    warnings = completion_warnings(draft, target_ids)

    def issue(node_id, field, code, message, item_id=None):
        issues.append({"nodeId": node_id, "fieldName": field, "itemId": item_id,
                       "code": code, "severity": "error", "message": message})

    if draft.schemaVersion != catalog["schemaVersion"] or draft.schemaHash != catalog["schemaHash"] or draft.rulesVersion != catalog["rulesVersion"]:
        issue(None, None, "SCHEMA_VERSION_MISMATCH", "스키마가 변경되었습니다. 새 초안에서 다시 확인해 주세요.")
        return {"valid": False, "finalizable": False, "issues": issues, "warnings": warnings, "artifacts": []}
    draft, allowed_managed, link_diagnostics = resolve_references(draft, target_ids, allow_unstored_files=True)
    warnings.extend(item for item in link_diagnostics if item["severity"] == "warning" and item["code"] != "FILE_STORAGE_PENDING")
    pending_storage = [item for item in link_diagnostics if item["code"] == "FILE_STORAGE_PENDING"]
    deferred_fields = {(item["nodeId"], item["fieldName"]) for item in pending_storage}
    link_issues = [item for item in link_diagnostics if item["severity"] == "error"]
    validation_scope = "partial-file-metadata" if pending_storage else "model-metadata-only"
    if link_issues:
        return {"valid": False, "finalizable": False, "issues": link_issues, "warnings": warnings,
                "pendingStorage": pending_storage, "artifacts": [], "validationScope": validation_scope}

    def build(node_id, ancestors):
        nonlocal visits
        visits += 1
        if visits > catalog["limits"]["maxNodes"]:
            if visits == catalog["limits"]["maxNodes"] + 1:
                issue(node_id, None, "EXPANSION_LIMIT", "객체 확장 제한을 초과했습니다.")
            return None
        if node_id in ancestors:
            issue(node_id, None, "CYCLIC_GRAPH", "객체가 자기 자신을 참조합니다.")
            return None
        if len(ancestors) >= catalog["limits"]["maxDepth"]:
            issue(node_id, None, "MAX_DEPTH", "객체 깊이 제한을 초과했습니다.")
            return None
        node = draft.nodes.get(node_id)
        if node is None:
            issue(node_id, None, "MISSING_NODE", "연결된 객체를 찾을 수 없습니다.")
            return None
        if node.typeId not in classes:
            issue(node_id, None, "UNKNOWN_TYPE", "지원하지 않는 타입입니다.")
            return None
        info = catalog["types"][node.typeId]
        by_name = {field["fieldName"]: field for field in info["fields"]}
        for name in node.fields.keys() - by_name.keys():
            issue(node_id, name, "UNKNOWN_FIELD", "이 타입에 없는 항목입니다.")
        values = {}
        for field in info["fields"]:
            name = field["fieldName"]
            present = name in node.fields
            value = node.fields.get(name)
            if not present or (isinstance(value, str) and not value.strip()):
                if node.typeId == "DtFile" and (node_id, name) in deferred_fields:
                    continue
                if field["required"]:
                    issue(node_id, name, "REQUIRED_FIELD", "필수 값을 입력해 주세요.")
                continue
            if field["managed"] and (node_id, name) not in allowed_managed:
                issue(node_id, name, "MANAGED_REFERENCE", "참조 연결 편집이 구현된 후 사용할 수 있습니다.")
                continue
            repeated = field["repeated"]
            if repeated != isinstance(value, list):
                issue(node_id, name, "CARDINALITY", "단일 값과 반복 값 형식을 확인해 주세요.")
                continue
            items = value if repeated else [value]
            if len(items) < field["minOccurs"] or (field["maxOccurs"] is not None and len(items) > field["maxOccurs"]):
                issue(node_id, name, "CARDINALITY", "항목 개수가 허용 범위와 다릅니다.")
                continue
            row_ids = [item.node if isinstance(item, NodeRef) else item.itemId for item in items] if repeated else []
            if len(set(row_ids)) != len(row_ids):
                issue(node_id, name, "DUPLICATE_ITEM", "반복 항목 ID가 중복됩니다.")
                continue
            converted = []
            for item in items:
                item_id = item.itemId if isinstance(item, ScalarItem) else item.node if isinstance(item, NodeRef) else None
                raw = item.value if isinstance(item, ScalarItem) else item
                if field["kind"] == "object":
                    target = draft.nodes.get(raw.node) if isinstance(raw, NodeRef) else None
                    allowed = {base for base in field["objectTypes"]}
                    allowed.update(child for base in field["objectTypes"] for child in catalog["types"][base]["descendants"])
                    if target is None or target.typeId not in allowed:
                        issue(node_id, name, "INVALID_OBJECT_TYPE", "허용된 하위 객체를 선택해 주세요.", item_id)
                        continue
                    converted.append(build(raw.node, ancestors + (node_id,)))
                elif field["kind"] == "enum":
                    enum_cls = getattr(model, field["enumTypes"][0])
                    try:
                        converted.append(enum_cls(raw))
                    except (ValueError, TypeError):
                        issue(node_id, name, "INVALID_ENUM", "허용된 enum 값을 선택해 주세요.", item_id)
                else:
                    actual = type(raw).__name__
                    valid = actual in field["scalarTypes"] or (actual == "int" and "float" in field["scalarTypes"])
                    if not valid:
                        issue(node_id, name, "INVALID_SCALAR", "값 타입을 확인해 주세요.", item_id)
                        continue
                    converted.append(raw)
            if len(converted) == len(items):
                values[name] = converted if repeated else converted[0]
        return classes[node.typeId](**values)

    assets = {asset.assetNodeId: asset for asset in draft.assets}
    for root_id in dict.fromkeys(target_ids):
        before = len(issues)
        asset = assets.get(root_id)
        root = draft.nodes.get(root_id)
        if asset is None or root is None or root.typeId != profile.assetType:
            issue(root_id, None, "INVALID_ASSET_ROOT", "올바른 자산 루트가 아닙니다.")
            continue
        element = draft.nodes.get(asset.elementNodeId)
        if element is None or element.typeId != profile.assetTypes[asset.role] or root.fields.get("schema_version") != profile.schemaVersion:
            issue(root_id, None, "ASSET_TYPE_MISMATCH", "자산 종류와 스키마 버전을 확인해 주세요.")
            continue
        elements = root.fields.get("dt_elements", [])
        if not isinstance(elements, list) or len(elements) != 1 or not isinstance(elements[0], NodeRef) or elements[0].node != asset.elementNodeId:
            issue(root_id, "dt_elements", "ASSET_ELEMENT_MISMATCH", "자산의 요소 연결을 확인해 주세요.")
            continue
        instance = build(root_id, ())
        if len(issues) != before:
            continue
        try:
            serializer = XmlSerializer(config=SerializerConfig(pretty_print=True))
            xml = serializer.render(instance, ns_map={None: profile.namespace, "xsi": "http://www.w3.org/2001/XMLSchema-instance"})
            XmlParser().from_string(xml, getattr(model, profile.assetType))
            omitted = [{"nodeId": item["nodeId"], "fieldName": item["fieldName"]}
                       for item in pending_storage if item["nodeId"] == asset.elementNodeId]
            artifacts.append({"assetNodeId": root_id, "xml": xml, "reviewOnly": True, "omittedFields": omitted})
        except Exception:
            # Do not expose raw model data or serializer tracebacks in the API response.
            issue(root_id, None, "SERIALIZATION_FAILED", "XML 변환에 실패했습니다. 타입과 필드를 확인해 주세요.")
    return {"valid": not issues, "finalizable": False, "validationScope": validation_scope,
            "issues": issues, "warnings": warnings, "pendingStorage": pending_storage, "machineReady": False, "artifacts": artifacts}
