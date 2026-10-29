"""Resolve declarative asset selections without persisting or mutating input."""
from urllib.parse import urlsplit

from src.services.creator.schema_provider import get_profile, policy_for, policy_hash


def reachable_nodes(nodes, roots):
    seen, stack = set(), list(roots)
    while stack:
        node_id = stack.pop()
        if node_id in seen or node_id not in nodes:
            continue
        seen.add(node_id)
        for value in nodes[node_id]["fields"].values():
            for item in value if isinstance(value, list) else [value]:
                if isinstance(item, dict) and "$node" in item:
                    stack.append(item["$node"])
    return seen


def resolve_asset_links(draft, target_ids, make_node):
    profile = get_profile()
    policies = {p.id: p for p in profile.referencePolicies}
    nodes = draft["nodes"]
    assets = {a["assetNodeId"]: a for a in draft["assets"]}
    reachable = reachable_nodes(nodes, assets)
    requested = reachable_nodes(nodes, target_ids)
    allowed, issues, seen = set(), [], set()

    def error(link, message, code="DT_LINK_INVALID"):
        policy = policies.get(link["policyId"])
        issues.append({"nodeId": link["sourceNodeId"], "fieldName": policy.fieldName if policy else None,
                       "itemId": None, "code": code, "severity": "error", "message": message})

    links = draft["referenceLinks"]
    if links and draft.get("referencePolicyHash") != policy_hash():
        error(links[0], "참조 정책이 변경되었습니다. 현재 설정으로 참조 연결을 다시 확인해 주세요.", "REFERENCE_POLICY_MISMATCH")
        return allowed, issues
    for link in links:
        source_id = link["sourceNodeId"]
        source = nodes.get(source_id)
        policy = policies.get(link["policyId"])
        # Orphan links must not silently disappear from a review.
        if source_id not in reachable:
            error(link, "참조를 소유한 객체가 삭제되었거나 자산 구조에서 분리되었습니다.")
            continue
        if source_id not in requested and link["targetAssetNodeId"] not in target_ids:
            continue
        if not policy or policy.editor != "asset-picker" or policy_for(source["typeId"], policy.fieldName) != policy:
            error(link, "이 객체에 사용할 수 없는 참조 정책입니다.")
            continue
        slot = (source_id, policy.fieldName)
        if slot in seen:
            error(link, "같은 항목에 참조가 중복 연결되었습니다.")
            continue
        seen.add(slot)
        if policy.fieldName in source["fields"]:
            error(link, "자산 선택 연결과 수동 참조 값을 동시에 입력할 수 없습니다.")
            continue
        target = assets.get(link["targetAssetNodeId"])
        root = nodes.get(target["assetNodeId"]) if target else None
        element = nodes.get(target["elementNodeId"]) if target else None
        if not target or target["role"] != policy.targetRole or not root or root["typeId"] != profile.assetType or not element or element["typeId"] != policy.targetType:
            error(link, "연결한 자산이 없거나 허용된 종류가 아닙니다. 참조 대상을 다시 선택해 주세요.")
            continue
        if root["fields"].get("schema_version") != profile.schemaVersion or root["fields"].get("dt_elements") != [{"$node": target["elementNodeId"]}]:
            error(link, "연결한 자산의 스키마 버전 또는 요소 연결이 올바르지 않습니다.")
            continue
        identity = (root["fields"].get("asset_global_id"), root["fields"].get("id"), element["fields"].get("element_id"))
        if not all(isinstance(v, str) and v.strip() for v in identity):
            error(link, "연결한 자산의 글로벌 ID·자산 ID·요소 ID를 입력해 주세요.")
            continue
        global_id, asset_id, element_id = (v.strip() for v in identity)
        try:
            uri = urlsplit(global_id)
        except ValueError:
            error(link, "연결 자산의 글로벌 ID 주소 형식이 올바르지 않습니다.")
            continue
        if uri.scheme not in ("http", "https") or not uri.netloc or uri.query or uri.fragment:
            error(link, "연결 자산의 글로벌 ID는 쿼리·프래그먼트 없는 HTTP(S) 주소여야 합니다.")
            continue
        fullpath = f'{global_id.rstrip("/")}/{asset_id}/{element_id}'
        for other in assets.values():
            if other["assetNodeId"] == target["assetNodeId"]:
                continue
            other_root, other_element = nodes.get(other["assetNodeId"], {}), nodes.get(other["elementNodeId"], {})
            values = (other_root.get("fields", {}).get("asset_global_id"), other_root.get("fields", {}).get("id"), other_element.get("fields", {}).get("element_id"))
            if all(isinstance(v, str) for v in values) and f'{values[0].strip().rstrip("/")}/{values[1].strip()}/{values[2].strip()}' == fullpath:
                error(link, "동일한 참조 주소를 가진 자산이 여러 개입니다. 자산 ID를 구분해 주세요.")
                break
        else:
            if source_id in requested:
                source["fields"][policy.fieldName] = make_node(profile.referenceType, {
                    "element_id": f"{policy.elementIdPrefix}-001", "category": "reference",
                    "display_name": policy.displayName,
                    "keys": [make_node(profile.keyValueType, {"key": policy.key, "value": fullpath})],
                })
                allowed.add(slot)
    return allowed, issues
