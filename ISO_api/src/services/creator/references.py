"""Resolve creator-only links into legacy DT references for a partial preview."""
from uuid import uuid4
from src.schemas.creator import CreatorDraft
from src.services.creator.cam import CamInputError
from src.services.creator.nc import asset_values, reference_id, tool_nodes, tool_values
from src.services.creator.asset_references import resolve_asset_links
from src.services.creator.schema_provider import get_profile, policy_for


def resolve_references(original, target_ids, *, allow_unstored_files=False):
    draft = original.model_dump(by_alias=True)
    nodes = draft["nodes"]
    assets = {asset["assetNodeId"]: asset for asset in draft["assets"]}
    allowed, issues = set(), []
    project_asset = assets.get(draft["projectAssetNodeId"])
    project = nodes.get(project_asset["elementNodeId"]) if project_asset else None
    root = nodes.get(draft["projectAssetNodeId"])

    def error(node_id, message):
        issues.append({"nodeId": node_id, "fieldName": None, "itemId": None, "code": "DT_LINK_INVALID", "severity": "error", "message": message})

    def make_node(type_id, fields):
        node_id = str(uuid4())
        nodes[node_id] = {"nodeId": node_id, "typeId": type_id, "fields": fields}
        return {"$node": node_id}

    def make_ref(element_id, keys):
        if not all(isinstance(value, str) and value.strip() for value in keys.values()):
            raise CamInputError("연결 자산의 글로벌 ID·자산 ID·요소 ID와 워크플랜 식별자를 입력해 주세요.")
        profile = get_profile()
        return make_node(profile.referenceType, {"element_id": element_id, "category": "reference", "keys": [make_node(profile.keyValueType, {"key": key, "value": value}) for key, value in keys.items()]})

    # Verify manual snapshots before any derived XML references are inserted.
    from src.services.creator.manual import resolve_manual
    manual_allowed, manual_issues = resolve_manual(draft, target_ids, make_node)
    allowed.update(manual_allowed)
    issues.extend(manual_issues)
    asset_allowed, asset_issues = resolve_asset_links(draft, target_ids, make_node)
    allowed.update(asset_allowed)
    issues.extend(asset_issues)

    project_requested = draft["projectAssetNodeId"] in target_ids
    file_links = draft["fileLinks"]
    for link in file_links:
        if link["assetNodeId"] not in target_ids:
            continue
        asset = assets.get(link["assetNodeId"])
        try:
            if not asset or asset["role"] != "file" or not project or not root:
                raise CamInputError("파일 자산 또는 프로젝트가 누락되었습니다.")
            element = nodes[asset["elementNodeId"]]
            if "value" in element["fields"]:
                raise CamInputError("로컬 파일에 저장 ID를 직접 지정할 수 없습니다. 최종 저장 시 발급됩니다.")
            if element["fields"].get("reference"):
                raise CamInputError("파일 연결과 수동 reference를 동시에 입력할 수 없습니다.")
            keys = {"DT_GLOBAL_ASSET": root["fields"].get("asset_global_id"), "DT_ASSET": root["fields"].get("id"), "DT_PROJECT": project["fields"].get("element_id")}
            if link["workplanNodeId"]:
                wp = nodes.get(link["workplanNodeId"])
                if not wp or wp["typeId"] != "Workplan":
                    raise CamInputError("파일에 배정한 워크플랜이 삭제되었습니다.")
                keys["WORKPLAN"] = wp["fields"].get("its_id")
            if link["purpose"] == "NC" and not link["workplanNodeId"]:
                raise CamInputError("NC 파일에 워크플랜을 배정해 주세요.")
            element["fields"]["reference"] = [make_ref("file-project-ref", keys)]
            # A browser Blob is not a GridFS OID; never invent a persisted file identifier.
            if not allow_unstored_files:
                raise CamInputError("파일 원본은 로컬에만 있습니다. dt_file.value 저장 ID는 최종 파일 저장 연동 후 생성됩니다.")
            issues.append({"nodeId": asset["elementNodeId"], "fieldName": "value", "itemId": None,
                           "code": "FILE_STORAGE_PENDING", "severity": "warning",
                           "message": "파일 저장 대기 · 검토용 XML에는 dt_file.value를 생략합니다. 최종 저장 후 실제 ID가 반영됩니다."})
        except (CamInputError, KeyError, TypeError, AttributeError, IndexError) as exc:
            error(asset["elementNodeId"] if asset else link["assetNodeId"], str(exc))

    seen_steps, seen_tools = set(), set()
    for link in draft["toolLinks"]:
        if link["workplanNodeId"] in draft["manualWorkplans"]:
            continue
        if not project_requested and link["assetNodeId"] not in target_ids:
            continue
        try:
            wp_id = link["workplanNodeId"]
            wp = nodes.get(wp_id)
            asset = assets.get(link["assetNodeId"])
            if not wp or wp["typeId"] != "Workplan" or not asset or asset["role"] != "tool":
                raise CamInputError("공구 연결 대상이 삭제되었습니다. NC 연결을 다시 확인해 주세요.")
            key = (wp_id, link["toolTag"])
            if key in seen_tools:
                raise CamInputError("같은 워크플랜/T 번호에 공구가 중복 연결되었습니다.")
            seen_tools.add(key)
            if not link["stepNodeIds"]:
                continue
            steps = [reference_id(ref) for ref in wp["fields"].get("its_elements", [])]
            steps = [step for step in steps if nodes.get(step, {}).get("typeId") in ("MachiningWorkingstep", "TurningWorkingstep")]
            linked_steps = [step for item in draft["toolLinks"] if item["workplanNodeId"] == wp_id for step in item["stepNodeIds"]]
            if len(linked_steps) != len(steps) or set(linked_steps) != set(steps):
                raise CamInputError("워크플랜의 모든 워킹스텝에 공구를 연결해 주세요.")
            reviews = [review for review in draft["ncReviews"] if review["workplanNodeId"] == wp_id]
            nc_files = [file for file in file_links if file["workplanNodeId"] == wp_id and file["purpose"] == "NC"]
            if len(reviews) != 1 or len(nc_files) != 1 or reviews[0]["stepNodeIds"] != steps or any(reviews[0][name] != nc_files[0][name] for name in ("fileId", "sha256")):
                raise CamInputError("NC 파일 또는 실행 순서가 변경되었습니다. NC 연결을 다시 확인해 주세요.")
            tool_root, element = nodes[asset["assetNodeId"]], nodes[asset["elementNodeId"]]
            if element["fields"].get("element_id") != link["toolTag"]:
                raise CamInputError("공구 요소 ID는 연결된 T 번호와 같아야 합니다.")
            canonical = asset_values(nodes, asset)
            for step in link["stepNodeIds"]:
                if step not in steps or step in seen_steps:
                    raise CamInputError("워킹스텝 공구 연결이 누락되거나 중복되었습니다.")
                seen_steps.add(step)
                if tool_values(nodes, step) != canonical:
                    raise CamInputError("13399 공구와 워킹스텝 공구값이 다릅니다. NC 연결에서 값을 확인해 주세요.")
                operation, _ = tool_nodes(nodes, step)
                policy = next((p for p in get_profile().referencePolicies if p.editor == "nc-tools" and policy_for(operation["typeId"], p.fieldName) == p), None)
                if policy is None:
                    raise CamInputError("이 가공 작업의 NC 공구 참조 정책이 없습니다.")
                if policy.fieldName in operation["fields"]:
                    raise CamInputError("공구 연결과 수동 ref_dt_cutting_tool을 동시에 입력할 수 없습니다.")
                global_id, asset_id = tool_root["fields"].get("asset_global_id", ""), tool_root["fields"].get("id", "")
                if not global_id or not asset_id:
                    raise CamInputError("공구 자산의 글로벌 ID와 자산 ID를 입력해 주세요.")
                uri = f'{global_id.rstrip("/")}/{asset_id}/{link["toolTag"]}'
                operation["fields"][policy.fieldName] = make_ref(link["toolTag"], {policy.key: uri})
                allowed.add((operation["nodeId"], policy.fieldName))
        except (CamInputError, KeyError, TypeError, AttributeError, IndexError) as exc:
            error(link["workplanNodeId"], str(exc))
    return CreatorDraft.model_validate(draft), allowed, issues
