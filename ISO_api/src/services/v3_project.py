from typing import Optional, List, Tuple, Dict, Any
import xmltodict
import re

from pymongo.errors import DuplicateKeyError
from motor.motor_asyncio import AsyncIOMotorCollection

from src.entities.asset import AssetRepository
from src.utils.v3_xml_parser import (
    extract_dtasset_meta,
    validate_xml_against_schema,
    get_inner_data,
    pick_dt_project,
    find_workplan_in_project,
    build_ref_url,
    find_workpiece_in_project,
    find_operation_in_workplan,
    append_multi_ref,
    remove_ref_by_uri,
)
from src.utils.exceptions import CustomException, ExceptionEnum
from src.utils.env import get_env_or_default
from src.schemas.asset import (
    AssetCreateRequest,
    AssetListResponse,
    AssetSearchQuery,
    AssetDocument,
)

import logging

logger = logging.getLogger(__name__)

# 타입/카테고리 규칙
REF_RULES: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {
    # type, category -> anchor, tag, key, requires
    ("dt_machine_tool", None): {
        "anchor": "workplan",
        "tag": "ref_dt_machine_tool",
        "key": "DT_MACHINE_TOOL",
        "requires": ["workplan_id"],
        "multi": False,
    },
    ("dt_material", None): {
        "anchor": "workpiece",
        "tag": "ref_dt_material",
        "key": "DT_MATERIAL",
        "requires": ["workpiece_id"],
        "multi": False,
    },
    ("dt_cutting_tool_13399", None): {
        "anchor": "operation",
        "tag": "ref_dt_cutting_tool",
        "key": "DT_CUTTING_TOOL_13399",
        "requires": ["workplan_id", "workingstep_id"],
        "multi": False,
    },
}


class V3ProjectService:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.repo = AssetRepository(collection)
        self.base_uri_prefix = get_env_or_default(
            "DT_BASE_URI_PREFIX", "https://digital-thread.re"
        )
        self.user_prefix = get_env_or_default("DT_USER_PREFIX", "kitech")

    async def exists_by_keys(self, xml_string: str):
        """
        xml string에 있는 키 조합이 이미 존재하는지 확인한다.
        """

        meta = extract_dtasset_meta(xml_string=xml_string)
        res = await self.repo.exists_by_keys(
            global_asset_id=meta["global_asset_id"],
            asset_id=meta["asset_id"],
            type=meta["type"],
            element_id=meta["element_id"],
        )

        # 중복이 없을 경우
        if res is None:
            return False
        else:
            # 중복이 있으면 바로 에러로 발생
            raise CustomException(ExceptionEnum.ASSET_ID_DUPLICATION)

    async def create_from_xml(self, xml: str):
        if not validate_xml_against_schema(xml):
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

        meta = extract_dtasset_meta(xml, strict=True)

        # 🔹 global_asset_id 보정
        normalized_global_id = self.normalize_global_asset_id(meta["global_asset_id"])
        if normalized_global_id != meta["global_asset_id"]:
            # XML 자체도 수정
            doc = xmltodict.parse(xml)
            if "dt_asset" in doc and "asset_global_id" in doc["dt_asset"]:
                doc["dt_asset"]["asset_global_id"] = normalized_global_id
            xml = xmltodict.unparse(doc)

        if meta["type"] != "dt_project":
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        return await self.repo.insert_asset(req=AssetCreateRequest(xml=xml))

    async def list_projects(
        self,
        *,
        global_asset_id: str,
        asset_id: Optional[str] = None,
    ) -> AssetListResponse:
        """
        - global_asset_id: 필수
        - asset_id, type: 선택 필터
        """

        query = AssetSearchQuery(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            type="dt_project",
        )
        rows = await self.repo.search_assets(query)

        # Pydantic v1/v2 호환
        parsed: List[AssetDocument]
        if hasattr(AssetDocument, "model_validate"):  # pydantic v2
            parsed = [AssetDocument.model_validate(r) for r in rows]
        else:  # pydantic v1
            parsed = [AssetDocument.parse_obj(r) for r in rows]

        return AssetListResponse(assets=parsed)

    async def get_by_keys(
        self, *, global_asset_id: str, asset_id: str, type: str, element_id: str
    ) -> Optional[dict]:
        return await self.repo.get_asset_by_keys(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            type=type,
            element_id=element_id,
        )

    async def extract_attribute_path(self, xml_string: str, path: str) -> str:
        """
        프로젝트의 속성을 추출한다.
        """

        return get_inner_data(project=xml_string, path=path)

    async def attach_ref(
        self,
        *,
        global_asset_id: str,
        asset_id: str,
        project_element_id: str,
        # 참조 대상
        ref_global_asset_id: str,
        ref_asset_id: str,
        ref_element_id: str,
        # 타입/카테고리 힌트
        ref_type: str,
        ref_category: Optional[str] = None,
        # 위치 파라미터(필요할 때만 사용)
        workplan_id: Optional[str] = None,
        workpiece_id: Optional[str] = None,
        workingstep_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        - 프로젝트(dt_project) XML에 참조를 추가(존재하는 앵커만 허용, 생성 없음)
        - 파일 계열(dt_file: NC/VM/TDMS)은 중복 URI 방지 후 append
        - 단일 계열(머신툴/머티리얼/커팅툴)은 덮어쓰기
        """
        # 0) 프로젝트 문서 조회
        project_doc = await self.repo.get_asset_by_keys(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            type="dt_project",
            element_id=project_element_id,
        )
        if not project_doc:
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)

        # ⛔️ 파일 계열 즉시 거절
        if ref_type == "dt_file":
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE,
                detail="project must not reference dt_file; files reference project instead",
            )

        # 1) 룰 선택
        rule = REF_RULES.get((ref_type, ref_category))
        if not rule:
            # 카테고리 생략했는데 파일 계열일 수 있으니 보정 시도
            if ref_type == "dt_file" and ref_category:
                rule = REF_RULES.get((ref_type, ref_category))
            if not rule:
                raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        # 2) 필수 파라미터 검사
        provided_params = {
            "workplan_id": workplan_id,
            "workpiece_id": workpiece_id,
            "workingstep_id": workingstep_id,
        }
        unknown = [k for k in rule.get("requires", []) if k not in provided_params]
        if unknown:
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE,
                detail=f"rule requires unknown param(s): {unknown}",
            )
        missing = [
            k for k in rule.get("requires", []) if self._blank(provided_params[k])
        ]
        if missing:
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE,
                detail=f"missing required params for {ref_type}{'/' + ref_category if ref_category else ''}: {missing}",
            )

        # 3) XML 파싱
        doc = xmltodict.parse(project_doc["data"])
        dt_proj = pick_dt_project(doc, project_element_id)

        # 4) 앵커 노드 선택 (예외 → 404)
        try:
            anchor = rule["anchor"]
            if anchor == "workplan":
                target = find_workplan_in_project(dt_proj, workplan_id)
            elif anchor == "workpiece":
                target = find_workpiece_in_project(dt_proj, workpiece_id)
            elif anchor == "operation":
                wp = find_workplan_in_project(dt_proj, workplan_id)
                target = find_operation_in_workplan(wp, workingstep_id)
            else:
                raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)
        except (KeyError, ValueError):
            # 지정한 workplan/workpiece/workingstep이 존재하지 않을 때
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)

        # 5) ref 객체 구성
        uri = build_ref_url(
            base_uri_prefix=self.base_uri_prefix,
            user_prefix=self.user_prefix,
            ref_global_asset_id=ref_global_asset_id,
            ref_asset_id=ref_asset_id,
            ref_element_id=ref_element_id,
        )
        ref_obj = {"keys": [{"key": rule["key"], "value": uri}]}

        # 6) 적용
        tag = rule["tag"]
        if rule.get("multi"):  # 파일 계열 → 중복 방지 append
            changed = append_multi_ref(target, tag, ref_obj)
            if not changed:
                # 같은 URI가 이미 존재
                raise CustomException(ExceptionEnum.REF_ALREADY_EXISTS)
        else:  # 단일 → 덮어쓰기
            before = target.get(tag)
            target[tag] = ref_obj
            changed = before != ref_obj

        # 7) 저장
        if changed:
            new_xml = xmltodict.unparse(doc)
            await self.repo.update_asset_xml_by_mongo_id(
                str(project_doc["_id"]), new_xml
            )

        return {
            "updated": bool(changed),
            "project_mongo_id": str(project_doc["_id"]),
        }

    async def remove_ref(
        self,
        *,
        global_asset_id: str,
        asset_id: str,
        project_element_id: str,
        # 참조 대상
        ref_global_asset_id: str,
        ref_asset_id: str,
        ref_element_id: str,
        # 타입/카테고리 힌트
        ref_type: str,
        ref_category: Optional[str] = None,
        # 위치 파라미터(필요할 때만 사용)
        workplan_id: Optional[str] = None,
        workpiece_id: Optional[str] = None,
        workingstep_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        - 프로젝트(dt_project) XML에서 참조(URI) 삭제
        - 추가 API와 동일한 파라미터 사용
        - 삭제 대상이 없으면 REF_NOT_FOUND
        """
        # 0) 프로젝트 문서 조회
        project_doc = await self.repo.get_asset_by_keys(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            type="dt_project",
            element_id=project_element_id,
        )
        if not project_doc:
            raise CustomException(
                ExceptionEnum.NO_DATA_FOUND, detail="project not found by keys"
            )
        # ⛔️ 파일 계열 즉시 거절
        if ref_type == "dt_file":
            # 과거에 잘못 저장된 파일 레퍼런스를 정리해야 한다면,
            # 별도의 정리 유틸을 만들어 직접 제거하세요(아래 주석 참고).
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE,
                detail="project no longer manages dt_file references",
            )

        # 1) 룰 선택 (파일 계열은 ref_category로 세분)
        rule = REF_RULES.get((ref_type, ref_category))
        if not rule:
            if ref_type == "dt_file" and ref_category:
                rule = REF_RULES.get((ref_type, ref_category))
        if not rule:
            msg = f"unsupported ref_type/category: ({ref_type}, {ref_category})"
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE, detail=msg)

        # 2) 필수 파라미터 검사
        provided_params = {
            "workplan_id": workplan_id,
            "workpiece_id": workpiece_id,
            "workingstep_id": workingstep_id,
        }
        unknown = [k for k in rule.get("requires", []) if k not in provided_params]
        if unknown:
            # 룰 정의가 잘못된 경우(디버깅용)
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE,
                detail=f"rule requires unknown param(s): {unknown}",
            )
        missing = [
            k for k in rule.get("requires", []) if self._blank(provided_params[k])
        ]
        if missing:
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE,
                detail=f"missing required params for {ref_type}{'/' + ref_category if ref_category else ''}: {missing}",
            )

        # 3) XML 파싱 및 project 선택
        doc = xmltodict.parse(project_doc["data"])
        dt_proj = pick_dt_project(doc, project_element_id)

        # 4) 앵커 노드 선택 (존재 필수)
        anchor = rule["anchor"]
        if anchor == "workplan":
            target = find_workplan_in_project(dt_proj, workplan_id)
        elif anchor == "workpiece":
            target = find_workpiece_in_project(dt_proj, workpiece_id)
        elif anchor == "operation":
            wp = find_workplan_in_project(dt_proj, workplan_id)
            target = find_operation_in_workplan(wp, workingstep_id)
        else:
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE, detail="anchor node not found"
            )

        # 5) 삭제할 URI 구성 (추가 때와 동일 포맷)
        uri = build_ref_url(
            base_uri_prefix=self.base_uri_prefix,
            user_prefix=self.user_prefix,
            ref_global_asset_id=ref_global_asset_id,
            ref_asset_id=ref_asset_id,
            ref_element_id=ref_element_id,
        )

        tag = rule["tag"]

        # 6) 삭제 수행
        removed = remove_ref_by_uri(target, tag, uri)

        if not removed:
            # 같은 위치/태그에 그 URI가 없었음
            raise CustomException(
                ExceptionEnum.REF_NOT_FOUND, detail=f"reference tag not found: {tag}"
            )

        # 7) 저장
        new_xml = xmltodict.unparse(doc)
        await self.repo.update_asset_xml_by_mongo_id(str(project_doc["_id"]), new_xml)

        return {
            "removed": True,
            "project_mongo_id": str(project_doc["_id"]),
        }

    # --- 내부 유틸 ---
    def _get_ref_rule(
        self, ref_type: str, ref_category: Optional[str]
    ) -> Dict[str, Any]:
        if ref_type == "dt_file":
            raise CustomException(
                ExceptionEnum.INVALID_ATTRIBUTE,
                detail="project must not reference dt_file",
            )
        key = (ref_type, (ref_category.upper() if ref_category else None))
        try:
            return REF_RULES[key]
        except KeyError:
            # 카테고리가 필수인데 안 들어온 경우 등도 여기서 걸림
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

    def _select_anchor_node(
        self,
        project_node: Dict[str, Any],
        rule: Dict[str, Any],
        *,
        workplan_id: Optional[str],
        workpiece_id: Optional[str],
        workingstep_id: Optional[str],
    ) -> Dict[str, Any]:
        anchor = rule["anchor"]
        if anchor == "workplan":
            if not workplan_id:
                raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)
            return find_workplan_in_project(
                project_node, workplan_id
            )  # (메인/its_elements 둘 다 탐색하는 버전)
        if anchor == "workpiece":
            if not workpiece_id:
                raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)
            return find_workpiece_in_project(
                project_node, workpiece_id
            )  # 존재해야 함(생성 X)
        if anchor == "operation":
            if not (workplan_id and workingstep_id):
                raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)
            wp = find_workplan_in_project(project_node, workplan_id)
            return find_operation_in_workplan(
                wp, workingstep_id
            )  # WS/OP 존재해야 함(생성 X)
        raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

    def _blank(self, x):
        return x is None or (isinstance(x, str) and x.strip() == "")

    async def get_nc_files_by_project(
        self,
        global_asset_id: str,
        asset_id: str,
        project_element_id: str,
        workplan_id: str,
    ) -> Dict[str, Any]:
        """
        지정된 프로젝트/워크플랜을 참조하는 NC 파일(dt_file)들을 검색해서 반환.
        """
        rows = await self.repo.find_nc_files_by_ref(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            project_element_id=project_element_id,
            workplan_id=workplan_id,
        )

        if not rows:
            raise CustomException(
                ExceptionEnum.NC_NOT_EXIST,
                f"No NC file referencing project={project_element_id}, wp={workplan_id}",
            )

        return {"count": len(rows), "items": rows}

    def normalize_global_asset_id(self, global_asset_id: str) -> str:
        """
        global_asset_id가 URI 형태인지 검사 후,
        아니라면 base_uri_prefix + user_prefix를 붙여서 URI로 변환한다.
        """
        if global_asset_id.startswith("http://") or global_asset_id.startswith(
            "https://"
        ):
            return global_asset_id
        # 기본 prefix 붙여서 URI로 만듦
        return f"{self.base_uri_prefix}/{self.user_prefix}/{global_asset_id}"
