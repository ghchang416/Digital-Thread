"""Keep authoring provenance separate from serialized ISO model fields."""
from src.schemas.creator import NodeRef


def completion_warnings(draft, target_ids):
    roots = list(target_ids)
    # A generated 13399 tool can inherit assumed values from its inline CAM tool.
    roots.extend(step for link in draft.toolLinks if link.assetNodeId in target_ids for step in link.stepNodeIds)
    reachable = set()
    while roots:
        id = roots.pop()
        if id in reachable or id not in draft.nodes:
            continue
        reachable.add(id)
        for value in draft.nodes[id].fields.values():
            roots.extend(item.node for item in (value if isinstance(value, list) else [value]) if isinstance(item, NodeRef))
    labels = {"placeholder": "작성용 임시값", "default": "작성용 기본값", "generated": "자동 생성", "batch": "공통 입력값"}
    warnings = []
    for entry in draft.completionEntries:
        if entry.nodeId not in reachable or entry.fieldName not in draft.nodes[entry.nodeId].fields:
            continue
        changed = draft.nodes[entry.nodeId].fields[entry.fieldName] != entry.value
        warnings.append({"nodeId": entry.nodeId, "fieldName": entry.fieldName, "itemId": None,
                         "code": "AUTHORING_" + entry.kind.upper(), "severity": "warning",
                         "message": f'{labels[entry.kind]}{" · 보완 후 변경됨" if changed else ""}: {entry.reason}'})
    return warnings
