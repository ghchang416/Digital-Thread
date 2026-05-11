# src/services/vm_project.py
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Mapping
import shutil
import json
import tempfile
import zipfile

import asyncio

import httpx
from bson import ObjectId
from fastapi import HTTPException

from src.core.config import settings
from src.dao.vm_project import VmProjectDAO
from src.schemas.vm_project import (
    ProcessItemIn,
    ProcessAnnotationItemOut,
    ProcessAnnotationsResponse,
    ProcessPatchIn,
    ProjectFileOut,
    StockInfo,
    StockPatchIn,
    VmResultUploadOut,
    VmResultUploadMode,
    VmProjectCreateIn,
    VmProjectListResponse,
    VmProjectListItem,
    VmProjectDetailOut,
    StockItemOut,
    StockItemsResponse,
    ToolpathPreviewOut,
)
from src.utils.nc_splitter import (
    extract_tool_numbers_from_paths,  # ([saved_paths]) -> List[int|None]
    process_nc_text,  # (nc_text: str, output_dir: str, base_filename_with_ext: str) -> List[str]
)
from src.utils.stock import lookup_stock_code, is_known_stock_code
from src.utils.toolpath_preview import (
    build_toolpath_preview_from_zip,
    parse_stock_box,
)
from src.utils.xml_parser import (
    extract_material_ref_from_project_xml,  # -> Optional[(gid, aid, eid)]
    extract_tool_refs_in_order,  # (project_xml, wpid) -> [{gid, aid, eid, tool_element_id, ...}]
    extract_stock_bounds_from_project_xml,  # -> Optional[{min_x, max_x, ...}]
    extract_project_summary,  # -> {display_name, description, main_wpid, ...}
    match_dt_file_refs,  # (parsed, gid=..., aid=..., eid=..., wpid=...)
    parse_cutting_tool_13399_xml,
    parse_dt_file_xml,
    parse_material_xml,
    make_vm_dt_file_xml,
)
from src.services.vm_file import VmFileService
from src.utils.stock import STOCK_ITEMS
import src.clients.dp as dp_client

import logging

logger = logging.getLogger(__name__)

# ---------------- 내부 유틸 (정규식) ----------------
_COORD_RE = re.compile(r"\b([xyz])\s+coordinates_mm\s*:\s*([+-]?\d+(?:\.\d+)?)", re.I)
_MIN_RE = re.compile(r"\bmin_([xyz])\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_MAX_RE = re.compile(r"\bmax_([xyz])\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_LEN_RE = re.compile(r"\b([xyz])\s*length_mm\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)

_STOCK_SIZE_6NUM_RE = re.compile(
    r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*"
    r"-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$"
)


def _dp_upstream_http_exception(context: str, exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc

    if isinstance(exc, httpx.HTTPStatusError):
        upstream_status = exc.response.status_code if exc.response else None
        if upstream_status == 404:
            status_code = 404
        elif upstream_status == 503:
            status_code = 503
        elif upstream_status and 500 <= upstream_status < 600:
            status_code = 502
        else:
            status_code = 502

        reason = ""
        if exc.response is not None:
            reason = exc.response.reason_phrase or ""
        detail = f"{context}: {upstream_status} {reason}".strip()
        return HTTPException(status_code=status_code, detail=detail)

    if isinstance(exc, httpx.HTTPError):
        return HTTPException(status_code=502, detail=f"{context}: {exc}")

    return HTTPException(status_code=502, detail=f"{context}: {exc}")


def _stock_from_material_xml(material_xml: str) -> StockInfo:
    parsed = parse_material_xml(material_xml)
    name_for_mapping = parsed.get("material_identifier") or parsed.get("display_name")
    code = lookup_stock_code(name_for_mapping)

    x_min = y_min = z_min = None
    x_max = y_max = z_max = None
    x_len = y_len = z_len = None
    coords = {"x": None, "y": None, "z": None}

    for raw in parsed.get("param_lines") or []:
        line = str(raw)
        m = _COORD_RE.search(line)
        if m:
            axis, val = m.group(1).lower(), float(m.group(2))
            coords[axis] = val
            continue
        m = _MIN_RE.search(line)
        if m:
            axis, val = m.group(1).lower(), float(m.group(2))
            if axis == "x":
                x_min = val
            elif axis == "y":
                y_min = val
            else:
                z_min = val
            continue
        m = _MAX_RE.search(line)
        if m:
            axis, val = m.group(1).lower(), float(m.group(2))
            if axis == "x":
                x_max = val
            elif axis == "y":
                y_max = val
            else:
                z_max = val
            continue
        m = _LEN_RE.search(line)
        if m:
            axis, val = m.group(1).lower(), float(m.group(2))
            if axis == "x":
                x_len = val
            elif axis == "y":
                y_len = val
            else:
                z_len = val
            continue

    # length* 가 있으면 (0, length)
    if x_len is not None:
        x_min, x_max = 0.0, x_len
    if y_len is not None:
        y_min, y_max = 0.0, y_len
    if z_len is not None:
        z_min, z_max = 0.0, z_len

    # coordinates_mm만 있으면 음수→(v,0), 양수→(0,v)
    for axis in ("x", "y", "z"):
        v = coords[axis]
        if v is None:
            continue
        if axis == "x" and x_min is None and x_max is None:
            x_min, x_max = (v, 0.0) if v < 0 else (0.0, v)
        if axis == "y" and y_min is None and y_max is None:
            y_min, y_max = (v, 0.0) if v < 0 else (0.0, v)
        if axis == "z" and z_min is None and z_max is None:
            z_min, z_max = (v, 0.0) if v < 0 else (0.0, v)

    # 한쪽만 있으면 다른쪽 0
    if x_min is not None and x_max is None:
        x_max = 0.0
    if y_min is not None and y_max is None:
        y_max = 0.0
    if z_min is not None and z_max is None:
        z_max = 0.0
    if x_max is not None and x_min is None:
        x_min = 0.0
    if y_max is not None and y_min is None:
        y_min = 0.0
    if z_max is not None and z_min is None:
        z_min = 0.0

    if None in (x_min, y_min, z_min, x_max, y_max, z_max):
        return StockInfo(
            stock_type=code,
            stock_size="0,0,0,0,0,0",
            reason="material_xml 파싱(길이/최소/최대 혼합 지원)",
        )

    # 좌표는 정수 좌표로 저장 (소수점 제거: 반올림 후 int)
    xi_min = int(round(x_min))
    xi_max = int(round(x_max))
    yi_min = int(round(y_min))
    yi_max = int(round(y_max))
    zi_min = int(round(z_min))
    zi_max = int(round(z_max))

    # 순서: x_min, x_max, y_min, y_max, z_min, z_max
    stock_size = f"{xi_min},{xi_max},{yi_min},{yi_max},{zi_min},{zi_max}"

    return StockInfo(
        stock_type=code, stock_size=stock_size, reason="material_xml 파싱 성공"
    )


class VmProjectService:
    def __init__(self, dao: VmProjectDAO, vm_file_svc: VmFileService):
        self.dao = dao
        self.vm_file_svc = vm_file_svc

    # ---------------- ISO HTTP ----------------
    async def _iso_get(
        self,
        path: str,
        *,
        path_params: Dict[str, str] | None = None,
        query: Dict[str, Any] | None = None,
    ) -> Any:
        base = str(settings.ISO_API_URL).rstrip("/")
        url = base + path.format(**(path_params or {}))
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(url, params=query or {})
            r.raise_for_status()
            return r.json()

    async def _fetch_project_xml(self, *, eid: str, gid: str, aid: str) -> str:
        data = await self._iso_get(
            settings.ISO_PATH_PROJECT_DETAIL,
            path_params={"element_id": eid},
            query={"global_asset_id": gid, "asset_id": aid},
        )
        return data.get("data") or ""

    async def _fetch_material_xml(
        self, *, eid: str, gid: str, aid: str
    ) -> Optional[str]:
        data = await self._iso_get(
            settings.ISO_PATH_ASSET_DETAIL,
            path_params={"element_id": eid},
            query={"global_asset_id": gid, "asset_id": aid, "type": "dt_material"},
        )
        return data.get("data") or None

    async def _fetch_tool_xml(self, *, eid: str, gid: str, aid: str) -> Optional[str]:
        data = await self._iso_get(
            settings.ISO_PATH_ASSET_DETAIL,
            path_params={"element_id": eid},
            query={
                "global_asset_id": gid,
                "asset_id": aid,
                "type": "dt_cutting_tool_13399",
            },
        )
        return data.get("data") or None

    async def _fetch_dt_file_xml(
        self, *, eid: str, gid: str, aid: str
    ) -> Optional[str]:
        data = await self._iso_get(
            settings.ISO_PATH_ASSET_DETAIL,
            path_params={"element_id": eid},
            query={"global_asset_id": gid, "asset_id": aid, "type": "dt_file"},
        )
        return data.get("data") or None

    async def _list_dt_file_element_ids(self, *, gid: str, aid: str) -> List[str]:
        data = await self._iso_get(
            settings.ISO_PATH_ASSET_LIST,
            query={"global_asset_id": gid, "asset_id": aid, "type": "dt_file"},
        )
        return data.get("data") or data.get("items") or []

    async def _download_nc_text_by_keys(self, *, gid: str, aid: str, eid: str) -> str:
        """
        GET {ISO_API_URL}{ISO_PATH_FILE_DOWNLOAD_BY_KEYS}
          ?global_asset_id=...&asset_id=...&element_id=...
        """
        base = str(settings.ISO_API_URL).rstrip("/")
        url = base + settings.ISO_PATH_FILE_DOWNLOAD_BY_KEYS
        async with httpx.AsyncClient(timeout=180.0) as client:
            r = await client.get(
                url,
                params={
                    "global_asset_id": gid,
                    "asset_id": aid,
                    "element_id": eid,
                },
            )
            r.raise_for_status()
            try:
                return r.text
            except Exception:
                return r.content.decode("utf-8", errors="ignore")

    # ---------------- Stock 계산 ----------------
    @staticmethod
    def _fmt_stock_size(bounds: Dict[str, float]) -> str:
        """bounds dict → "min_x,max_x,min_y,max_y,min_z,max_z" 정수 문자열."""
        return ",".join(
            str(int(round(bounds[k])))
            for k in ("min_x", "max_x", "min_y", "max_y", "min_z", "max_z")
        )

    async def compute_stock_auto(self, payload: VmProjectCreateIn) -> StockInfo:
        proj_xml = await self._fetch_project_xml(
            eid=payload.eid, gid=payload.gid, aid=payload.aid
        )

        # 소재 크기: project XML의 its_workpieces + its_workpiece_setup 기반
        bounds = extract_stock_bounds_from_project_xml(proj_xml)
        stock_size = self._fmt_stock_size(bounds) if bounds else None

        # 소재 타입 코드: dt_material의 material_identifier에서 매핑
        stock_type = None
        mat_ref = extract_material_ref_from_project_xml(proj_xml)
        if mat_ref:
            gid2, aid2, eid2 = mat_ref
            gid2 = gid2 or payload.gid
            aid2 = aid2 or payload.aid
            mxml = await self._fetch_material_xml(eid=eid2, gid=gid2, aid=aid2)
            if mxml:
                parsed = parse_material_xml(mxml)
                name = parsed.get("material_identifier") or parsed.get("display_name")
                stock_type = lookup_stock_code(name)

        if bounds:
            reason = "project XML bounding geometry 추출 성공"
        else:
            reason = "its_workpieces/its_workpiece_setup 단서 없음"

        return StockInfo(stock_type=stock_type, stock_size=stock_size, reason=reason)

    # ---------------- 프로젝트 파일 빌더 ----------------
    def _build_project_file(
        self, stock: StockInfo, process: Optional[List[ProcessItemIn]] = None
    ) -> ProjectFileOut:
        procs = process or []
        return ProjectFileOut(
            stock_type=stock.stock_type,
            stock_size=stock.stock_size,
            process_count=len(procs),
            process=procs,
        )

    @staticmethod
    def _normalize_project_file_dict(data: Mapping[str, Any] | None) -> dict[str, Any]:
        """
        레거시 project_file_draft 호환용 정규화.
        - stock_type이 숫자형으로 저장된 예전 문서를 문자열로 변환
        """
        normalized = dict(data or {})
        stock_type = normalized.get("stock_type")
        if isinstance(stock_type, (int, float)) and not isinstance(stock_type, bool):
            normalized["stock_type"] = str(int(stock_type))
        return normalized

    @staticmethod
    def _build_process_annotations(ws_refs: list[dict]) -> list[dict]:
        return [
            {
                "index": idx,
                "workingstep_id": w.get("ws_id"),
                "tool_element_id": w.get("tool_element_id") or w.get("eid"),
            }
            for idx, w in enumerate(ws_refs)
        ]

    async def _rebuild_process_annotations_from_source(self, doc: dict) -> list[dict]:
        source = str(doc.get("source") or "iso").strip().lower()
        gid = str(doc.get("gid") or "").strip()
        aid = str(doc.get("aid") or "").strip()
        eid = str(doc.get("eid") or "").strip()
        wpid = doc.get("wpid")

        if not gid or not aid or not eid:
            return []

        if source == "dp":
            proj_xml = await dp_client.get_element_xml(aid=aid, eid=eid)
        else:
            proj_xml = await self._fetch_project_xml(eid=eid, gid=gid, aid=aid)

        if not proj_xml:
            return []

        ws_refs = extract_tool_refs_in_order(proj_xml, wpid)
        return self._build_process_annotations(ws_refs)

    @staticmethod
    def _resolve_upload_mode_from_doc(doc: Mapping[str, Any] | None) -> str:
        mode = str((doc or {}).get("upload_mode") or "").strip().lower()
        if mode in {m.value for m in VmResultUploadMode}:
            return mode
        upload_result = (doc or {}).get("upload_result")
        return (
            VmResultUploadMode.file.value
            if upload_result is not False
            else VmResultUploadMode.link.value
        )

    @staticmethod
    def _empty_vm_result_upload(mode: str) -> dict[str, Any]:
        return {
            "mode": mode,
            "seq_id": None,
            "total_count": 0,
            "uploaded_indices": [],
            "uploaded_element_ids": [],
            "last_uploaded_index": None,
            "last_uploaded_element_id": None,
            "failed_index": None,
            "error_message": None,
            "updated_at": datetime.now().isoformat(),
        }

    # ---------------- DB 초안 생성/조회/패치 ----------------
    async def create_from_iso(
        self, payload: VmProjectCreateIn
    ) -> Tuple[ObjectId, StockInfo, ProjectFileOut]:
        stock = await self.compute_stock_auto(payload)
        pf = self._build_project_file(stock, process=[])
        _id = await self.dao.insert_draft_from_iso(
            source="iso",
            gid=payload.gid,
            aid=payload.aid,
            eid=payload.eid,
            wpid=payload.wpid,
            project_file_draft=pf.model_dump(),
        )
        return _id, stock, pf

    async def get_project_file(
        self, _id: ObjectId, *, source: str = "draft"
    ) -> ProjectFileOut:
        if source == "file":
            merged = await self._load_current_project_json(
                _id
            )  # 파일 있으면 파일, 없으면 draft 반환
            return ProjectFileOut(**merged)
        # 기본: draft
        doc = await self.dao.get(_id)
        pf = self._normalize_project_file_dict(
            (doc or {}).get("project_file_draft") or {}
        )
        return ProjectFileOut(**pf)

    async def get_process_annotations(
        self, _id: ObjectId
    ) -> ProcessAnnotationsResponse:
        doc = await self.dao.get(_id)
        if not doc:
            raise HTTPException(status_code=404, detail="vm_project not found")

        items = doc.get("process_annotations") or []
        if not items:
            items = await self._rebuild_process_annotations_from_source(doc)
            if items:
                await self.dao.update_process_annotations(_id, items)

        return ProcessAnnotationsResponse(
            items=[ProcessAnnotationItemOut(**item) for item in items]
        )

    async def patch_stock(self, _id: ObjectId, patch: StockPatchIn) -> ProjectFileOut:
        # --- 0) 스톡 코드 사전 검증: 미정의 코드면 차단 ---
        if patch.stock_type is not None and not is_known_stock_code(patch.stock_type):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": f"unknown stock_type: {patch.stock_type}",
                    "hint": "사전에 정의된 스톡 코드만 허용됩니다. /api/v1/vm-project/stocks 로 목록을 확인하세요.",
                },
            )

        # 🔽 상태 체크 (ready / needs-fix만 허용)
        doc = await self._ensure_editable_status(_id)
        pf = self._normalize_project_file_dict(
            (doc or {}).get("project_file_draft") or {}
        )

        # --- DB 초안: stock 필드만 교체 ---
        changed: dict[str, object] = {}
        if patch.stock_type is not None:
            pf["stock_type"] = patch.stock_type
            changed["stock_type"] = patch.stock_type
        if patch.stock_size is not None:
            pf["stock_size"] = patch.stock_size
            changed["stock_size"] = patch.stock_size

        await self.dao.update_project_file_draft(_id, pf)

        # --- 파일: stock 필드만 머지 ---
        try:
            res = await self._write_project_json_merged(_id, changed)
            merged = res["merged"]
        except HTTPException:
            # 파일이 아직 없을 수 있음(초기 단계) → 이 경우 파일 생성 스킵하고 draft만 유지
            merged = pf

        # --- 유효성 재검증은 머지된 최종 JSON 기준 ---
        pf_model = ProjectFileOut(**merged)
        validation_errors = self._validate_project_file(pf_model)
        await self.dao.set_validation_result(
            _id,
            is_valid=(len(validation_errors) == 0),
            errors=validation_errors,
            next_status_if_valid="ready",
            next_status_if_invalid="needs-fix",
        )
        return pf_model

    async def patch_process(
        self, _id: ObjectId, patch: ProcessPatchIn
    ) -> ProjectFileOut:
        # 🔽 상태 체크 (ready / needs-fix만 허용)
        doc = await self._ensure_editable_status(_id)
        pf = self._normalize_project_file_dict(
            (doc or {}).get("project_file_draft") or {}
        )

        # --- DB 초안: process 필드만 교체 ---
        new_list = [p.model_dump() for p in patch.process]
        pf["process"] = new_list
        pf["process_count"] = len(new_list)
        await self.dao.update_project_file_draft(_id, pf)

        # --- 파일: process 필드만 머지 ---
        try:
            res = await self._write_project_json_merged(
                _id,
                {"process": new_list, "process_count": len(new_list)},
            )
            merged = res["merged"]
        except HTTPException:
            merged = pf

        # --- 유효성 재검증(머지된 최종 JSON 기준) ---
        pf_model = ProjectFileOut(**merged)
        validation_errors = self._validate_project_file(pf_model)
        await self.dao.set_validation_result(
            _id,
            is_valid=(len(validation_errors) == 0),
            errors=validation_errors,
            next_status_if_valid="ready",
            next_status_if_invalid="needs-fix",
        )
        return pf_model

    async def _ensure_editable_status(self, _id: ObjectId) -> dict:
        """
        stock / process 수정이 가능한 상태인지 검사.
        - 허용: status == 'ready' 또는 'needs-fix'
        - 그 외: 400 에러
        """
        doc = await self.dao.get(_id)
        if not doc:
            raise HTTPException(status_code=404, detail="vm_project not found")

        status = (doc.get("status") or "").strip()

        if status not in ("ready", "needs-fix"):
            # completed / running / failed / draft 등은 수정 불가
            raise HTTPException(
                status_code=400,
                detail={
                    "message": (
                        "stock/process 수정은 status가 'ready' 또는 'needs-fix'일 때만 가능합니다."
                    ),
                    "status": status,
                },
            )

        return doc

    # ---------------- 라우터용 미리보기(빈 process) ----------------
    async def preview_from_iso(
        self, payload: VmProjectCreateIn
    ) -> Tuple[StockInfo, ProjectFileOut]:
        stock = await self.compute_stock_auto(payload)
        pf = self._build_project_file(stock, process=[])
        return stock, pf

    # ---------------- 풀 파이프라인 미리보기 (NC 포함) ----------------
    async def preview_from_iso_with_nc(
        self, payload: VmProjectCreateIn
    ) -> Tuple[StockInfo, ProjectFileOut, Dict]:
        """
        - stock 계산
        - (main 또는 하위 workplan)에서 WS 순서대로 tool refs 추출
        - dt_file 선택(프로젝트/워크플랜 키 매칭) → 키 기반 파일 다운로드
        - NC 분할 저장 (tmp/<projname>/ncdata/원본명_1/원본명_1.확장자 ...)
        - WS 수 == 분할 수 검증
        - 각 WS의 tool XML 파싱 → tool_data 구성
        - process 채워 ProjectFileOut 반환
        - 추가: ncdata.zip 생성, project.prj 생성
        """
        debug: Dict[str, Any] = {}

        # 1) 프로젝트 XML
        proj_xml = await self._fetch_project_xml(
            eid=payload.eid, gid=payload.gid, aid=payload.aid
        )
        debug["display_name"] = extract_project_summary(proj_xml).get("display_name")

        # 2) 워크플랜 확인/WS 추출
        ws_refs = extract_tool_refs_in_order(
            proj_xml, wpid=payload.wpid
        )  # [{gid, aid, eid, tool_element_id, ...}]
        debug["process_annotations"] = self._build_process_annotations(ws_refs)
        if payload.wpid:
            wp_id = re.escape(payload.wpid)
            main_hit = re.search(
                rf"<main_workplan>.*?<its_id>\s*{wp_id}\s*</its_id>",
                proj_xml,
                re.DOTALL | re.IGNORECASE,
            )
            child_hit = re.search(
                rf"<main_workplan>.*?<its_elements[^>]*xsi:type=\"workplan\"[^>]*>.*?<its_id>\s*{wp_id}\s*</its_id>",
                proj_xml,
                re.DOTALL | re.IGNORECASE,
            )
            if not (main_hit or child_hit):
                raise HTTPException(
                    status_code=404,
                    detail=f"workplan its_id='{payload.wpid}' not found under main_workplan",
                )
        debug["ws_count"] = len(ws_refs)

        # 3) 소재
        stock = await self.compute_stock_auto(payload)

        # 4) (aid, eid) 후보 수집 (gid 기준)
        pairs = await self._list_dtfile_pairs(gid=payload.gid)
        if not pairs:
            raise ValueError("dt_file 후보를 찾지 못했습니다.")

        # 5) 키 매칭되는 dt_file 선정
        matched_eid: Optional[str] = None
        matched_aid: Optional[str] = None
        matched_info: Optional[Dict[str, Any]] = None

        for aid_try, eid_try in pairs:
            try:
                xml = await self._fetch_dt_file_xml(
                    eid=eid_try, gid=payload.gid, aid=aid_try
                )
            except Exception:
                continue
            if not xml:
                continue

            info = parse_dt_file_xml(xml) or {}
            if match_dt_file_refs(
                info,
                gid=payload.gid,
                aid=payload.aid,
                eid=payload.eid,
                wpid=payload.wpid,
            ):
                matched_eid = info.get("element_id") or eid_try
                matched_aid = aid_try
                matched_info = info
                break

        if not matched_eid or not matched_aid or not matched_info:
            raise ValueError(
                "프로젝트/워크플랜 키와 일치하는 dt_file을 찾지 못했습니다."
            )

        # 👉 여기 추가: 매칭된 원본 dt_file의 aid/eid를 debug에 기록
        debug["dt_file"] = {"aid": matched_aid, "eid": matched_eid}

        # 6) 파일 다운로드
        nc_text = await self._download_nc_text_by_keys(
            gid=payload.gid, aid=matched_aid, eid=matched_eid
        )
        if not nc_text:
            raise ValueError("dt_file 다운로드 실패")

        # 7) 분할 저장 (tmp/<proj>/ncdata/…)
        proj_name = self._create_vm_project_name()
        work_dir = os.path.join("tmp", proj_name)
        ncdata_dir = os.path.join(work_dir, "ncdata")
        os.makedirs(ncdata_dir, exist_ok=True)

        base_filename_with_ext = matched_info.get("display_name") or "program.nc"
        saved_paths = process_nc_text(
            nc_text, ncdata_dir, base_filename_with_ext=base_filename_with_ext
        )
        debug["proj_name"] = proj_name
        debug["work_dir"] = work_dir
        debug["nc_saved_count"] = len(saved_paths)
        debug["nc_saved_sample"] = saved_paths[:2]

        # 8) WS 수 == 분할 수
        if len(saved_paths) != len(ws_refs):
            raise ValueError(
                f"워킹스텝 수({len(ws_refs)})와 NC 분할 수({len(saved_paths)}) 불일치"
            )

        # 9) 툴 번호 비교
        nc_tools = extract_tool_numbers_from_paths(saved_paths)
        ws_tools_num: List[Optional[int]] = []
        for w in ws_refs:
            t_eid = w.get("tool_element_id") or w.get("eid")
            num = None
            if isinstance(t_eid, str):
                m = re.search(r"T(\d+)$", t_eid.strip(), re.IGNORECASE)
                if m:
                    num = int(m.group(1))
            ws_tools_num.append(num)
        debug["nc_tools"] = nc_tools
        debug["ws_tools"] = ws_tools_num

        # NC 툴번호와 워킹스텝 툴번호 일치 여부 검사
        mismatch_errors = self._compare_tool_numbers(nc_tools, ws_tools_num)
        debug["tool_numbers_ok"] = len(mismatch_errors) == 0
        debug["tool_number_mismatches"] = mismatch_errors

        # 10) process (상대경로 규칙 반영)
        process_items: List[ProcessItemIn] = []
        for idx, w in enumerate(ws_refs):
            tnum = nc_tools[idx] if nc_tools[idx] is not None else ws_tools_num[idx]

            eff = cr = teeth = None
            gid_t = w.get("gid") or payload.gid
            aid_t = w.get("aid") or payload.aid
            eid_t = w.get("eid") or w.get("tool_element_id")
            if eid_t and gid_t and aid_t:
                tool_xml = await self._fetch_tool_xml(eid=eid_t, gid=gid_t, aid=aid_t)
                if tool_xml:
                    parsed = parse_cutting_tool_13399_xml(tool_xml) or {}
                    vals = parsed.get("values") or {}
                    eff = vals.get("effective_cutting_diameter")
                    cr = vals.get("corner_radius")
                    teeth = vals.get("number_of_teeth")

            half_minus_cr = (
                (eff / 2 - cr)
                if (isinstance(eff, (int, float)) and isinstance(cr, (int, float)))
                else None
            )

            def _fmt6(x: Optional[float]) -> str:
                if not isinstance(x, (int, float)):
                    return "null"
                return str(int(x)) if x % 1 == 0 else "{:g}".format(x)

            tool_data = ",".join(
                [
                    str(tnum) if tnum is not None else "null",
                    _fmt6(eff),
                    _fmt6(cr),
                    _fmt6(half_minus_cr),
                    _fmt6(cr),
                    "null",
                    "null",
                    "null",
                    _fmt6(teeth),
                ]
            )

            # 경로 규칙
            abs_path = saved_paths[idx]
            rel_path = os.path.relpath(abs_path, start=work_dir)
            rel_path_win = rel_path.replace("/", "\\")
            stem = os.path.splitext(os.path.basename(rel_path))[0]
            out_dir_win = os.path.join("result", stem).replace("/", "\\")

            process_items.append(
                ProcessItemIn(
                    file_path=rel_path_win,  # "ncdata\\...\\...nc"
                    output_dir_path=out_dir_win,  # "result\\<stem>"
                    tool_data=tool_data,
                )
            )

        project_file = ProjectFileOut(
            stock_type=stock.stock_type,
            stock_size=stock.stock_size,
            process_count=len(process_items),
            process=process_items,
        )

        # 11) ncdata.zip — root_dir=ncdata_dir 로 압축 시 분할폴더가 zip 최상위에 위치
        zip_out = os.path.join(work_dir, "ncdata")
        archive_path = shutil.make_archive(
            zip_out, "zip", root_dir=ncdata_dir
        )
        debug["ncdata_zip"] = archive_path

        # 12) project.prj
        iso_proj_eid = payload.eid or "project"
        prj_path = self._write_project_prj(work_dir, iso_proj_eid, project_file)
        debug["project_prj"] = prj_path

        return stock, project_file, debug

    # ---------------- 기타 ----------------
    def _create_vm_project_name(self) -> str:
        now = datetime.now()
        ampm = "pp" if now.hour >= 12 else "ap"
        hour12 = now.hour % 12 or 12
        return f"{now.year}-{now.month:02d}-{now.day:02d}_{ampm}_{hour12}_{now.minute:02d}_{now.second:02d}"

    async def _build_process_from_workplan(
        self,
        proj_xml: str,
        wpid: Optional[str],
        *,
        default_gid: Optional[str] = None,
        default_aid: Optional[str] = None,
    ) -> List[ProcessItemIn]:
        """
        선택된 워크플랜의 워킹스텝 순서대로 tool_data만 채워 ProcessItemIn 리스트 생성.
        - file_path/output_dir_path는 None (NC 분할 전 미리보기 용도)
        - ws에 gid/aid/eid가 있으면 그걸 사용하고, 없으면 default_*를 사용(없으면 툴 XML 조회 스킵)
        """

        def _fmt6(x: Optional[float]) -> str:
            return "{:.6f}".format(x) if isinstance(x, (int, float)) else "null"

        ws_list = extract_tool_refs_in_order(proj_xml, wpid)
        out: List[ProcessItemIn] = []

        for ws in ws_list:
            gid_t = ws.get("gid") or default_gid
            aid_t = ws.get("aid") or default_aid
            eid_t = ws.get("eid") or ws.get("tool_element_id")

            eff = cr = teeth = None
            if gid_t and aid_t and eid_t:
                tool_xml = await self._fetch_tool_xml(eid=eid_t, gid=gid_t, aid=aid_t)
                if tool_xml:
                    parsed = parse_cutting_tool_13399_xml(tool_xml) or {}
                    vals = parsed.get("values") or {}
                    eff = vals.get("effective_cutting_diameter")
                    cr = vals.get("corner_radius")
                    teeth = vals.get("number_of_teeth")

            half_minus_cr = (
                (eff / 2 - cr)
                if (isinstance(eff, (int, float)) and isinstance(cr, (int, float)))
                else None
            )

            # T번호는 여기선 알 수 없으므로 null. (NC 분할 후에는 NC에서 추출한 번호를 사용)
            tool_data = ",".join(
                [
                    "null",  # tool_no
                    _fmt6(eff),
                    _fmt6(cr),
                    _fmt6(half_minus_cr),
                    _fmt6(cr),
                    "null",
                    "null",
                    "null",
                    _fmt6(teeth),
                ]
            )

            out.append(
                ProcessItemIn(
                    file_path=None,
                    output_dir_path=None,
                    tool_data=tool_data,
                )
            )

        return out

    async def _list_dtfile_pairs(self, *, gid: str) -> List[tuple[str, str]]:
        """
        GET /api/v3/assets?global_asset_id=...&type=dt_file
        -> [(aid, eid), ...] 반환
        """
        data = await self._iso_get(
            settings.ISO_PATH_ASSET_LIST,  # 보통 "/api/v3/assets"
            query={"global_asset_id": gid, "type": "dt_file"},
        )
        assets = data.get("assets") or data.get("data") or data.get("items") or []
        pairs: List[tuple[str, str]] = []
        for a in assets:
            if not isinstance(a, dict):
                continue
            if (a.get("type") or "").strip() != "dt_file":
                continue
            aid = (a.get("asset_id") or "").strip()
            eid = (a.get("element_id") or "").strip()
            if aid and eid:
                pairs.append((aid, eid))
        return pairs

    def _unique_basename(self, dirpath: str, basename_no_ext: str, ext: str) -> str:
        """
        dirpath 안에서 basename_no_ext.ext 와 충돌나면 -2, -3 ... suffix 붙여 유니크 파일명 반환
        반환: 절대경로 (dirpath/basename.ext)
        """
        candidate = os.path.join(dirpath, f"{basename_no_ext}{ext}")
        if not os.path.exists(candidate):
            return candidate
        i = 2
        while True:
            cand = os.path.join(dirpath, f"{basename_no_ext}-{i}{ext}")
            if not os.path.exists(cand):
                return cand
            i += 1

    def _write_project_prj(
        self, work_dir: str, base_name: str, project_file: ProjectFileOut
    ) -> str:
        """
        work_dir 안에 <base_name>.prj (충돌 시 -N)로 저장.
        project_file(model) 내용을 JSON으로 덤프.
        """
        prj_path = self._unique_basename(work_dir, base_name, ".prj")
        data = project_file.model_dump()
        with open(prj_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return prj_path

    async def create_full_from_iso(self, payload: VmProjectCreateIn) -> dict:
        """
        1) stock/project_file 계산 + nc 분할(zip), project.prj 생성
        2) vm_project 문서 생성(초기 상태)
        3) GridFS 업로드 + vm_file 2건 생성
        4) vm_project.latest_files 포인터 갱신 + 상태 'ready'
        5) (추가) tmp/<proj_name> 작업 디렉토리 정리
        """
        # 1) 파일 생성 단계
        stock, project_file, debug = await self.preview_from_iso_with_nc(payload)
        zip_path = debug["ncdata_zip"]  # tmp/<proj>/ncdata.zip
        prj_path = debug["project_prj"]  # tmp/<proj>/<eid>[ -N].prj
        proj_name = debug.get("proj_name")
        display_name = debug.get("display_name")
        dtfile_meta = debug.get("dt_file") or {}
        process_annotations = debug.get("process_annotations") or []
        work_dir = debug.get("work_dir")  # 👈 tmp/<proj_name>

        try:
            # 2) vm_project 생성 (초기)
            vm_project_id = await self.dao.insert_initial_from_iso(
                source="iso",
                gid=payload.gid,
                aid=payload.aid,
                eid=payload.eid,
                wpid=payload.wpid,
                project_file_draft=project_file.model_dump(),
                process_annotations=process_annotations,
                proj_name=proj_name,
                display_name=display_name,
            )

            # 3) GridFS 업로드 + vm_file 생성
            # 3-1) ncdata.zip (파일명은 무조건 'ncdata.zip')
            zip_vm_file_id = await self.vm_file_svc.create_from_path(
                vm_project_id=vm_project_id,
                kind="nc-split-zip",
                file_path=zip_path,
                original_name="ncdata.zip",  # <- 고정
                content_type="application/zip",
                meta={
                    "source": "iso",
                    "gid": payload.gid,
                    "aid": payload.aid,
                    "eid": payload.eid,
                    "wpid": payload.wpid,
                    "dt_file": {  # 어떤 원본 dt_file에서 분할했는지 추적
                        "aid": dtfile_meta.get("aid"),
                        "eid": dtfile_meta.get("eid"),
                    },
                },
            )

            # 3-2) project.prj (JSON 내용, 파일명은 실제 생성된 이름 기록)
            prj_vm_file_id = await self.vm_file_svc.create_from_path(
                vm_project_id=vm_project_id,
                kind="vm-project-json",
                file_path=prj_path,
                original_name=os.path.basename(prj_path),
                content_type="application/octet-stream",
                meta={
                    "source": "iso",
                    "gid": payload.gid,
                    "aid": payload.aid,
                    "eid": payload.eid,
                    "wpid": payload.wpid,
                    "process_count": project_file.process_count,
                },
            )

            # 4) vm_project 최신 포인터/상태 갱신
            await self.dao.set_latest_files(
                vm_project_id,
                {
                    "nc-split-zip": zip_vm_file_id,
                    "vm-project-json": prj_vm_file_id,
                },
            )

            # 5) 유효성 검사 → 상태 반영
            validation_errors = self._validate_project_file(project_file)

            tool_mismatch_errors = debug.get("tool_number_mismatches") or []
            if tool_mismatch_errors:
                validation_errors.extend(tool_mismatch_errors)

            await self.dao.set_validation_result(
                vm_project_id,
                is_valid=(len(validation_errors) == 0),
                errors=validation_errors,
                next_status_if_valid="ready",
                next_status_if_invalid="needs-fix",
            )

            return {
                "vm_project_id": str(vm_project_id),
                "status": "ready" if not validation_errors else "needs-fix",
                "files": {
                    "nc_split_zip_id": str(zip_vm_file_id),
                    "project_json_id": str(prj_vm_file_id),
                },
                "validation": {
                    "is_valid": len(validation_errors) == 0,
                    "errors": validation_errors,
                },
                "debug": debug,
            }

        finally:
            # ✅ tmp/<proj_name> 정리 (성공/실패 상관없이 시도)
            if work_dir and os.path.isdir(work_dir):
                try:
                    shutil.rmtree(work_dir)
                    logger.info("Cleaned up tmp work_dir: %s", work_dir)
                except Exception as e:
                    logger.warning("Failed to cleanup tmp work_dir %s: %s", work_dir, e)

    # ================================================================
    # DP 파이프라인
    # ================================================================

    async def _preview_from_dp_with_nc(
        self, payload: VmProjectCreateIn
    ) -> Tuple[StockInfo, ProjectFileOut, Dict]:
        """
        DP 데이터 소스 기반 풀 파이프라인 (ISO 버전인 preview_from_iso_with_nc의 DP 버전).
        소재/공구 조회 실패 시 graceful degradation → needs-fix.
        """
        debug: Dict[str, Any] = {}

        # 1) 프로젝트 XML
        try:
            proj_xml = await dp_client.get_element_xml(aid=payload.aid, eid=payload.eid)
        except Exception as e:
            raise _dp_upstream_http_exception("DP 프로젝트 xml 조회 실패", e) from e
        if not proj_xml:
            raise ValueError("DP에서 프로젝트 xmlStr을 가져오지 못했습니다.")
        debug["display_name"] = extract_project_summary(proj_xml).get("display_name")

        # 2) WS 추출
        ws_refs = extract_tool_refs_in_order(proj_xml, wpid=payload.wpid)
        debug["ws_count"] = len(ws_refs)
        debug["process_annotations"] = self._build_process_annotations(ws_refs)

        # 3) 소재 크기: project XML에서 직접 추출 (예외 없음)
        bounds = extract_stock_bounds_from_project_xml(proj_xml)
        stock_size = self._fmt_stock_size(bounds) if bounds else None

        # 4) 소재 타입 코드: dt_material API 조회 (실패해도 graceful)
        # DP API는 aid를 "gid/aid" 형태의 전체 URL로 요구
        stock_type = None
        try:
            mat_ref = extract_material_ref_from_project_xml(proj_xml)
            if mat_ref:
                mat_gid, mat_aid, mat_eid = mat_ref
                mat_gid = mat_gid or payload.gid
                dp_mat_aid = f"{mat_gid}/{mat_aid}" if mat_aid else mat_gid
                mat_xml = await dp_client.get_element_xml(aid=dp_mat_aid, eid=mat_eid)
                if mat_xml:
                    parsed = parse_material_xml(mat_xml)
                    name = parsed.get("material_identifier") or parsed.get("display_name")
                    stock_type = lookup_stock_code(name)
        except Exception as e:
            logger.warning("DP 소재 타입 조회 실패(graceful): %s", e)

        reason = "project XML bounding geometry 추출 성공" if bounds else "its_workpieces/its_workpiece_setup 단서 없음"
        stock = StockInfo(stock_type=stock_type, stock_size=stock_size, reason=reason)

        # 4) DP gid 기준으로 file 타입 element 목록 조회
        try:
            gid_elements = await dp_client.list_elements_by_gid(payload.gid)
        except Exception as e:
            raise _dp_upstream_http_exception("DP element 목록 조회 실패", e) from e

        file_items = [
            item for item in (gid_elements.get("content") or [])
            if (item.get("type") or "").lower() == "file"
        ]
        if not file_items:
            raise ValueError("DP에서 dt_file 후보를 찾지 못했습니다.")

        # 5) dt_file 매칭 (xmlStr로 parse_dt_file_xml + match_dt_file_refs 재사용)
        matched_item: Optional[Dict[str, Any]] = None
        matched_info: Optional[Dict[str, Any]] = None
        xml_fetch_errors: list[tuple[str, Exception]] = []

        for item in file_items:
            item_aid = item.get("assetId") or ""
            item_eid = item.get("elementId") or ""
            if not item_aid or not item_eid:
                continue
            try:
                xml = await dp_client.get_element_xml(aid=item_aid, eid=item_eid)
            except Exception as e:
                logger.warning("DP dt_file xml 조회 실패(graceful skip): %s", e)
                xml_fetch_errors.append((item_eid, e))
                continue
            if not xml:
                continue
            info = parse_dt_file_xml(xml) or {}
            if self._match_dt_file_dp(info, gid=payload.gid, eid=payload.eid, wpid=payload.wpid):
                matched_item = item
                matched_info = info
                break

        if not matched_item or not matched_info:
            if xml_fetch_errors:
                failed_eids = ", ".join(eid for eid, _ in xml_fetch_errors[:5])
                context = "DP dt_file xml 조회 실패"
                if failed_eids:
                    context = f"{context} ({failed_eids})"
                raise _dp_upstream_http_exception(context, xml_fetch_errors[0][1]) from xml_fetch_errors[0][1]
            raise ValueError("프로젝트/워크플랜 키와 일치하는 dt_file을 찾지 못했습니다.")

        nc_path = matched_item.get("path") or ""
        if not nc_path:
            raise ValueError("매칭된 dt_file의 path가 비어 있습니다.")

        debug["dt_file"] = {
            "aid": matched_item.get("assetId"),
            "eid": matched_item.get("elementId"),
            "path": nc_path,
        }

        # 6) NC 다운로드
        try:
            nc_text = await dp_client.download_nc_file(nc_path)
        except Exception as e:
            raise _dp_upstream_http_exception("DP NC 파일 다운로드 실패", e) from e
        if not nc_text:
            raise ValueError("NC 파일 다운로드 실패 (빈 응답)")

        # 7) NC 분할
        proj_name = self._create_vm_project_name()
        work_dir = os.path.join("tmp", proj_name)
        ncdata_dir = os.path.join(work_dir, "ncdata")
        os.makedirs(ncdata_dir, exist_ok=True)

        base_filename = matched_info.get("display_name") or matched_item.get("elementId") or "program.nc"
        saved_paths = process_nc_text(nc_text, ncdata_dir, base_filename_with_ext=base_filename)

        debug["proj_name"] = proj_name
        debug["work_dir"] = work_dir
        debug["nc_saved_count"] = len(saved_paths)

        # 8) WS 수 == 분할 수 검증
        if len(saved_paths) != len(ws_refs):
            raise ValueError(
                f"워킹스텝 수({len(ws_refs)})와 NC 분할 수({len(saved_paths)}) 불일치"
            )

        # 9) 툴 번호 비교
        nc_tools = extract_tool_numbers_from_paths(saved_paths)
        ws_tools_num: List[Optional[int]] = []
        for w in ws_refs:
            t_eid = w.get("tool_element_id") or w.get("eid")
            num = None
            if isinstance(t_eid, str):
                m = re.search(r"T(\d+)$", t_eid.strip(), re.IGNORECASE)
                if m:
                    num = int(m.group(1))
            ws_tools_num.append(num)

        mismatch_errors = self._compare_tool_numbers(nc_tools, ws_tools_num)
        debug["tool_numbers_ok"] = len(mismatch_errors) == 0
        debug["tool_number_mismatches"] = mismatch_errors

        # 10) process 생성 (공구 조회 실패 → null 채움, graceful)
        process_items: List[ProcessItemIn] = []
        tool_fetch_failures: list[dict[str, Any]] = []
        for idx, w in enumerate(ws_refs):
            tnum = nc_tools[idx] if nc_tools[idx] is not None else ws_tools_num[idx]

            eff = cr = teeth = None
            ws_id = w.get("ws_id")
            tool_eid = w.get("eid") or w.get("tool_element_id")
            tool_short_aid = w.get("aid")
            tool_gid = w.get("gid") or payload.gid
            # DP API는 aid를 "gid/aid" 형태의 전체 URL로 요구
            tool_aid = f"{tool_gid}/{tool_short_aid}" if tool_short_aid else None

            if tool_eid and tool_aid:
                try:
                    tool_xml = await dp_client.get_element_xml(aid=tool_aid, eid=tool_eid)
                    if tool_xml:
                        parsed = parse_cutting_tool_13399_xml(tool_xml) or {}
                        vals = parsed.get("values") or {}
                        eff = vals.get("effective_cutting_diameter")
                        cr = vals.get("corner_radius")
                        teeth = vals.get("number_of_teeth")
                    else:
                        failure = {
                            "process_index": idx + 1,
                            "workingstep_id": ws_id,
                            "tool_asset_id": tool_aid,
                            "tool_element_id": tool_eid,
                            "reason": "empty_xml",
                        }
                        tool_fetch_failures.append(failure)
                        logger.warning(
                            "DP 공구 XML 비어 있음(graceful) process=%s ws_id=%s aid=%s eid=%s",
                            idx + 1,
                            ws_id,
                            tool_aid,
                            tool_eid,
                        )
                except Exception as e:
                    failure = {
                        "process_index": idx + 1,
                        "workingstep_id": ws_id,
                        "tool_asset_id": tool_aid,
                        "tool_element_id": tool_eid,
                        "reason": "fetch_error",
                        "error": str(e),
                    }
                    tool_fetch_failures.append(failure)
                    logger.warning(
                        "DP 공구 조회 실패(graceful) process=%s ws_id=%s aid=%s eid=%s: %s",
                        idx + 1,
                        ws_id,
                        tool_aid,
                        tool_eid,
                        e,
                    )

            half_minus_cr = (
                (eff / 2 - cr)
                if (isinstance(eff, (int, float)) and isinstance(cr, (int, float)))
                else None
            )

            def _fmt6(x: Optional[float]) -> str:
                if not isinstance(x, (int, float)):
                    return "null"
                return str(int(x)) if x % 1 == 0 else "{:g}".format(x)

            tool_data = ",".join([
                str(tnum) if tnum is not None else "null",
                _fmt6(eff), _fmt6(cr), _fmt6(half_minus_cr), _fmt6(cr),
                "null", "null", "null",
                _fmt6(teeth),
            ])

            abs_path = saved_paths[idx]
            rel_path = os.path.relpath(abs_path, start=work_dir)
            rel_path_win = rel_path.replace("/", "\\")
            stem = os.path.splitext(os.path.basename(rel_path))[0]
            out_dir_win = os.path.join("result", stem).replace("/", "\\")

            process_items.append(
                ProcessItemIn(
                    file_path=rel_path_win,
                    output_dir_path=out_dir_win,
                    tool_data=tool_data,
                )
            )

        if tool_fetch_failures:
            debug["tool_fetch_failures"] = tool_fetch_failures
            debug["tool_fetch_failure_count"] = len(tool_fetch_failures)

        project_file = ProjectFileOut(
            stock_type=stock.stock_type,
            stock_size=stock.stock_size,
            process_count=len(process_items),
            process=process_items,
        )

        # 11) ncdata.zip + project.prj — root_dir=ncdata_dir 로 압축 시 분할폴더가 zip 최상위에 위치
        zip_out = os.path.join(work_dir, "ncdata")
        archive_path = shutil.make_archive(zip_out, "zip", root_dir=ncdata_dir)
        debug["ncdata_zip"] = archive_path

        prj_path = self._write_project_prj(work_dir, payload.eid or "project", project_file)
        debug["project_prj"] = prj_path

        return stock, project_file, debug

    async def create_full_from_dp(self, payload: VmProjectCreateIn) -> dict:
        """
        DP 데이터 소스 기반 VM 프로젝트 생성 (ISO 버전인 create_full_from_iso의 DP 버전).
        """
        stock, project_file, debug = await self._preview_from_dp_with_nc(payload)
        zip_path = debug["ncdata_zip"]
        prj_path = debug["project_prj"]
        proj_name = debug.get("proj_name")
        display_name = debug.get("display_name")
        dtfile_meta = debug.get("dt_file") or {}
        process_annotations = debug.get("process_annotations") or []
        work_dir = debug.get("work_dir")

        try:
            vm_project_id = await self.dao.insert_initial_from_iso(
                source="dp",
                gid=payload.gid,
                aid=payload.aid,
                eid=payload.eid,
                wpid=payload.wpid,
                project_file_draft=project_file.model_dump(),
                process_annotations=process_annotations,
                proj_name=proj_name,
                display_name=display_name,
            )

            zip_vm_file_id = await self.vm_file_svc.create_from_path(
                vm_project_id=vm_project_id,
                kind="nc-split-zip",
                file_path=zip_path,
                original_name="ncdata.zip",
                content_type="application/zip",
                meta={
                    "source": "dp",
                    "gid": payload.gid,
                    "aid": payload.aid,
                    "eid": payload.eid,
                    "wpid": payload.wpid,
                    "dt_file": {
                        "aid": dtfile_meta.get("aid"),
                        "eid": dtfile_meta.get("eid"),
                    },
                },
            )

            prj_vm_file_id = await self.vm_file_svc.create_from_path(
                vm_project_id=vm_project_id,
                kind="vm-project-json",
                file_path=prj_path,
                original_name=os.path.basename(prj_path),
                content_type="application/octet-stream",
                meta={
                    "source": "dp",
                    "gid": payload.gid,
                    "aid": payload.aid,
                    "eid": payload.eid,
                    "wpid": payload.wpid,
                    "process_count": project_file.process_count,
                },
            )

            await self.dao.set_latest_files(
                vm_project_id,
                {
                    "nc-split-zip": zip_vm_file_id,
                    "vm-project-json": prj_vm_file_id,
                },
            )

            validation_errors = self._validate_project_file(project_file)
            tool_mismatch_errors = debug.get("tool_number_mismatches") or []
            if tool_mismatch_errors:
                validation_errors.extend(tool_mismatch_errors)

            await self.dao.set_validation_result(
                vm_project_id,
                is_valid=(len(validation_errors) == 0),
                errors=validation_errors,
                next_status_if_valid="ready",
                next_status_if_invalid="needs-fix",
            )

            return {
                "vm_project_id": str(vm_project_id),
                "status": "ready" if not validation_errors else "needs-fix",
                "files": {
                    "nc_split_zip_id": str(zip_vm_file_id),
                    "project_json_id": str(prj_vm_file_id),
                },
                "validation": {
                    "is_valid": len(validation_errors) == 0,
                    "errors": validation_errors,
                },
                "debug": debug,
            }

        finally:
            if work_dir and os.path.isdir(work_dir):
                try:
                    shutil.rmtree(work_dir)
                except Exception as e:
                    logger.warning("Failed to cleanup tmp work_dir %s: %s", work_dir, e)

    _DP_NC_CATEGORIES = {"NC", "NCCODE", "nc", "nccode"}
    _DP_TITLE_IMAGE_CATEGORY = "TITLE_IMAGE"

    @classmethod
    def _match_dt_file_dp(
        cls, info: dict, *, gid: str, eid: str, wpid: Optional[str]
    ) -> bool:
        """
        DP dt_file 매칭. ISO와 달리 DT_ASSET 키에 full URI가 아닌 short ID가 저장되므로
        DT_GLOBAL_ASSET + DT_PROJECT + WORKPLAN 세 키만 비교한다.
        category가 NC/NCCODE가 아닌 파일(STEP 등)은 제외한다.
        """
        category = (info or {}).get("category") or ""
        if category not in cls._DP_NC_CATEGORIES:
            return False
        refs = (info or {}).get("refs") or {}
        if (refs.get("DT_GLOBAL_ASSET") or "") != (gid or ""):
            return False
        if (refs.get("DT_PROJECT") or "") != (eid or ""):
            return False
        if wpid:
            return (refs.get("WORKPLAN") or "") == wpid
        return True

    @staticmethod
    def _dp_asset_ref_matches(ref_aid: str | None, project_aid: str | None) -> bool:
        """
        DP dt_file reference의 DT_ASSET은 short id와 full URI가 섞일 수 있어
        full match 또는 마지막 path segment match를 모두 허용한다.
        """
        ref = (ref_aid or "").strip()
        project = (project_aid or "").strip()
        if not ref or not project:
            return True
        if ref == project:
            return True
        return ref == project.rstrip("/").split("/")[-1]

    @classmethod
    def _match_dp_title_image(
        cls, info: dict, *, gid: str, aid: str, eid: str
    ) -> bool:
        category = str((info or {}).get("category") or "").strip().upper()
        if category != cls._DP_TITLE_IMAGE_CATEGORY:
            return False
        refs = (info or {}).get("refs") or {}
        if (refs.get("DT_GLOBAL_ASSET") or "") != (gid or ""):
            return False
        if (refs.get("DT_PROJECT") or "") != (eid or ""):
            return False
        return cls._dp_asset_ref_matches(refs.get("DT_ASSET"), aid)

    @staticmethod
    def _parse_dp_datetime(value: Any) -> float:
        if not isinstance(value, str) or not value.strip():
            return 0.0
        try:
            return datetime.fromisoformat(value.strip()).timestamp()
        except ValueError:
            return 0.0

    @staticmethod
    def _is_image_path(value: Any) -> bool:
        if not isinstance(value, str):
            return False
        return value.lower().split("?", 1)[0].endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
        )

    @classmethod
    def _dp_title_image_priority(cls, *, info: dict, item: dict, path: str) -> tuple:
        """
        TITLE_IMAGE 후보가 여러 개일 때 대표 썸네일을 안정적으로 고르기 위한 정렬 키.

        우선순위:
        1) content_type이 image/*인 후보
        2) content_type이 없지만 path/display_name이 이미지 확장자인 후보
        3) updateDate 최신
        4) createDate 최신
        5) assetSeq 큰 값
        6) elementId 사전순
        """
        content_type = str(info.get("content_type") or "").strip().lower()
        display_name = info.get("display_name") or item.get("displayName")

        image_score = 0
        if content_type.startswith("image/"):
            image_score = 2
        elif cls._is_image_path(path) or cls._is_image_path(display_name):
            image_score = 1

        try:
            asset_seq = int(item.get("assetSeq") or 0)
        except (TypeError, ValueError):
            asset_seq = 0

        return (
            image_score,
            cls._parse_dp_datetime(item.get("updateDate")),
            cls._parse_dp_datetime(item.get("createDate")),
            asset_seq,
            str(item.get("elementId") or info.get("element_id") or ""),
        )

    async def get_dp_project_thumbnail(
        self, *, gid: str, aid: str, eid: str
    ) -> tuple[bytes, str]:
        """
        DP 원본 프로젝트(gid/aid/eid)의 TITLE_IMAGE 썸네일을 반환한다.
        생성 wizard에서 DP 프로젝트 선택 단계에서 사용한다.
        """
        if not (gid and aid and eid):
            raise HTTPException(status_code=404, detail="thumbnail not available")

        try:
            gid_elements = await dp_client.list_elements_by_gid(gid)
        except Exception as e:
            raise HTTPException(
                status_code=502, detail=f"DP element 목록 조회 실패: {e}"
            )

        candidates: list[dict[str, Any]] = []

        for item in gid_elements.get("content") or []:
            if not isinstance(item, dict):
                continue

            item_type = str(item.get("type") or "").strip().lower()
            if item_type and item_type not in {"file", "dt_file"}:
                continue

            item_aid = item.get("assetId") or item.get("aid") or ""
            item_eid = item.get("elementId") or item.get("eid") or ""
            if not item_aid or not item_eid:
                continue

            try:
                xml = await dp_client.get_element_xml(aid=item_aid, eid=item_eid)
            except Exception:
                continue
            if not xml:
                continue

            info = parse_dt_file_xml(xml) or {}
            if not self._match_dp_title_image(info, gid=gid, aid=aid, eid=eid):
                continue

            path = info.get("path") or item.get("path")
            if not path:
                continue

            content_type = str(info.get("content_type") or "").strip().lower()
            if content_type and not content_type.startswith("image/"):
                continue

            candidates.append(
                {
                    "item": item,
                    "info": info,
                    "path": path,
                    "priority": self._dp_title_image_priority(
                        info=info, item=item, path=path
                    ),
                }
            )

        last_download_error: Exception | None = None
        for candidate in sorted(
            candidates, key=lambda c: c["priority"], reverse=True
        ):
            info = candidate["info"]
            path = candidate["path"]

            try:
                content, response_content_type = (
                    await dp_client.download_user_file_bytes(path)
                )
            except Exception as e:
                last_download_error = e
                continue

            media_type = (
                info.get("content_type")
                or response_content_type
                or "application/octet-stream"
            )
            return content, str(media_type).split(";")[0]

        if candidates and last_download_error is not None:
            raise HTTPException(
                status_code=502,
                detail=f"DP thumbnail 다운로드 실패: {last_download_error}",
            )

        raise HTTPException(status_code=404, detail="thumbnail not found")

    async def get_thumbnail(self, _id: ObjectId) -> tuple[bytes, str]:
        """
        VM 프로젝트 썸네일을 반환한다.
        현재는 DP source만 지원하며, 기존 VM 생성/NC 매칭 경로와 독립적으로 동작한다.
        """
        doc = await self.dao.get(_id)
        if not doc:
            raise HTTPException(status_code=404, detail="vm_project not found")

        source = (doc.get("source") or "iso").strip().lower()
        if source != "dp":
            raise HTTPException(status_code=404, detail="thumbnail not available")

        return await self.get_dp_project_thumbnail(
            gid=doc.get("gid") or "",
            aid=doc.get("aid") or "",
            eid=doc.get("eid") or "",
        )

    def _validate_project_file(self, pf: ProjectFileOut) -> list[str]:
        errors: list[str] = []

        # stock
        if pf.stock_type is None:
            errors.append("stock_type is empty")
        elif not is_known_stock_code(pf.stock_type):
            errors.append(f"stock_type {pf.stock_type} is not allowed")

        if not pf.stock_size or not _STOCK_SIZE_6NUM_RE.match(pf.stock_size):
            errors.append(
                "stock_size must be 6 numbers separated by commas (x_min,x_max,y_min,y_max,z_min,z_max)"
            )

        # process/tool_data
        if not isinstance(pf.process, list) or len(pf.process) == 0:
            errors.append("process is empty")
        else:
            for i, p in enumerate(pf.process, start=1):
                if not p.file_path:
                    errors.append(f"process[{i}].file_path is empty")
                if not p.output_dir_path:
                    errors.append(f"process[{i}].output_dir_path is empty")
                if not p.tool_data or "null" in p.tool_data.lower():
                    errors.append(f"process[{i}].tool_data contains null or is empty")
                parts = [x.strip() for x in (p.tool_data or "").split(",")]
                if len(parts) != 9:
                    errors.append(
                        f"process[{i}].tool_data must have 9 comma-separated fields"
                    )

        return errors

    async def list_projects(
        self,
        *,
        status: str | None = None,
        gid: str | None = None,
        aid: str | None = None,
        q: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> VmProjectListResponse:
        docs, total = await self.dao.list_projects(
            status=status, gid=gid, aid=aid, q=q, page=page, size=size
        )
        items: list[VmProjectListItem] = []
        for d in docs:
            val = d.get("validation") or {}
            errors = val.get("errors") or []
            items.append(
                VmProjectListItem(
                    id=str(d.get("_id")),
                    status=d.get("status"),
                    source=d.get("source") or "iso",
                    proj_name=d.get("proj_name"),
                    display_name=d.get("display_name"),
                    gid=d.get("gid"),
                    aid=d.get("aid"),
                    eid=d.get("eid"),
                    wpid=d.get("wpid"),
                    created_at=d.get("created_at"),
                    updated_at=d.get("updated_at"),
                    validation_is_valid=val.get("is_valid"),
                    validation_error_count=(
                        len(errors) if isinstance(errors, list) else 0
                    ),
                )
            )
        has_more = (page * size) < total
        return VmProjectListResponse(
            total=total, page=page, size=size, has_more=has_more, items=items
        )

    async def get_detail(self, _id: ObjectId) -> VmProjectDetailOut:
        doc = await self.dao.get(_id)
        if not doc:
            raise HTTPException(status_code=404, detail="vm_project not found")

        # latest_files 의 ObjectId → str 변환
        lf_raw = doc.get("latest_files") or {}
        latest_files: dict[str, str] = {}
        for k, v in lf_raw.items():
            try:
                latest_files[k] = str(v)
            except Exception:
                # 혹시 이미 string이면 그대로
                latest_files[k] = v if isinstance(v, str) else ""

        val = doc.get("validation") or {}
        errors = val.get("errors") or []
        is_valid = val.get("is_valid")

        pf_dict = self._normalize_project_file_dict(
            doc.get("project_file_draft") or {}
        )
        project_file = ProjectFileOut(**pf_dict)

        # 👇 vm 필드 추출
        vm_job_id = doc.get("vm_job_id")
        vm_last_polled_at = doc.get("vm_last_polled_at")
        vm_error_message = doc.get("vm_error_message")
        vm_raw_status = doc.get("vm_raw_status")
        upload_mode = self._resolve_upload_mode_from_doc(doc)
        vm_result_upload_raw = doc.get("vm_result_upload")
        vm_result_upload = (
            VmResultUploadOut(**vm_result_upload_raw)
            if isinstance(vm_result_upload_raw, dict)
            else None
        )

        return VmProjectDetailOut(
            id=str(doc.get("_id")),
            status=doc.get("status"),
            source=doc.get("source") or "iso",
            proj_name=doc.get("proj_name"),
            display_name=doc.get("display_name"),
            gid=doc.get("gid"),
            aid=doc.get("aid"),
            eid=doc.get("eid"),
            wpid=doc.get("wpid"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            latest_files=latest_files,
            validation_is_valid=is_valid,
            validation_errors=errors if isinstance(errors, list) else [],
            project_file_draft=project_file,
            vm_job_id=str(vm_job_id) if vm_job_id is not None else None,
            vm_last_polled_at=vm_last_polled_at,
            vm_error_message=vm_error_message,
            vm_raw_status=vm_raw_status,
            upload_mode=upload_mode,
            vm_result_upload=vm_result_upload,
        )

    async def get_toolpath_preview(
        self,
        _id: ObjectId,
        *,
        max_segments: int = 20000,
        include_rapid: bool = True,
        process_index: Optional[int] = None,
    ) -> ToolpathPreviewOut:
        doc = await self.dao.get(_id)
        if not doc:
            raise HTTPException(status_code=404, detail="vm_project not found")

        max_segments = min(50000, max(1, int(max_segments)))
        errors: list[str] = []

        pf_dict = self._normalize_project_file_dict(
            doc.get("project_file_draft") or {}
        )
        project_file = ProjectFileOut(**pf_dict)
        stock, stock_error = parse_stock_box(project_file.stock_size)
        if stock_error:
            errors.append(stock_error)

        latest = doc.get("latest_files") or {}
        nc_file_id = latest.get("nc-split-zip")
        if not nc_file_id:
            errors.append("nc-split-zip file is not available")
            return ToolpathPreviewOut(
                stock=stock,
                toolpath_bounds=None,
                segments=[],
                files=[],
                summary={
                    "segment_count": 0,
                    "returned_segment_count": 0,
                    "truncated": False,
                    "sampling": "none",
                    "max_segments": max_segments,
                    "process_count": project_file.process_count,
                    "type_counts": {},
                    "errors": errors,
                },
            )

        try:
            vm_file_id = (
                nc_file_id
                if isinstance(nc_file_id, ObjectId)
                else ObjectId(str(nc_file_id))
            )
        except Exception as e:
            errors.append(f"invalid nc-split-zip file id: {e}")
            return ToolpathPreviewOut(
                stock=stock,
                toolpath_bounds=None,
                segments=[],
                files=[],
                summary={
                    "segment_count": 0,
                    "returned_segment_count": 0,
                    "truncated": False,
                    "sampling": "none",
                    "max_segments": max_segments,
                    "process_count": project_file.process_count,
                    "type_counts": {},
                    "errors": errors,
                },
            )

        vmf_doc = await self.vm_file_svc.dao.get(vm_file_id)
        if not vmf_doc or not vmf_doc.get("gridfs_id"):
            errors.append("nc-split-zip vm_file or gridfs_id is missing")
            return ToolpathPreviewOut(
                stock=stock,
                toolpath_bounds=None,
                segments=[],
                files=[],
                summary={
                    "segment_count": 0,
                    "returned_segment_count": 0,
                    "truncated": False,
                    "sampling": "none",
                    "max_segments": max_segments,
                    "process_count": project_file.process_count,
                    "type_counts": {},
                    "errors": errors,
                },
            )

        try:
            zip_bytes = await self.vm_file_svc.filestore.gfs_get_bytes(
                vmf_doc["gridfs_id"]
            )
            preview = await asyncio.to_thread(
                build_toolpath_preview_from_zip,
                zip_bytes=zip_bytes,
                processes=project_file.process,
                max_segments=max_segments,
                include_rapid=include_rapid,
                process_index=process_index,
            )
        except zipfile.BadZipFile:
            errors.append("nc-split-zip is not a valid zip file")
            preview = self._empty_toolpath_preview(max_segments, project_file.process_count)
        except Exception as e:
            logger.exception("Toolpath preview build failed: %s", e)
            errors.append(f"toolpath preview failed: {e}")
            preview = self._empty_toolpath_preview(max_segments, project_file.process_count)

        preview["stock"] = stock
        preview["summary"]["errors"] = [
            *errors,
            *[
                f"process {item.get('process_index')}: {item.get('error')}"
                for item in preview.get("files", [])
                if item.get("error")
            ],
        ]
        return ToolpathPreviewOut(**preview)

    @staticmethod
    def _empty_toolpath_preview(max_segments: int, process_count: int) -> dict:
        return {
            "toolpath_bounds": None,
            "segments": [],
            "files": [],
            "summary": {
                "segment_count": 0,
                "returned_segment_count": 0,
                "truncated": False,
                "sampling": "none",
                "max_segments": max_segments,
                "process_count": process_count,
                "type_counts": {},
            },
        }

    async def list_stock_items(self, q: str | None = None) -> StockItemsResponse:
        """
        utils/stock.py 의 STOCK_ITEMS 를 그대로 보여준다.
        - q가 있으면 간단 필터(코드는 정확 일치, 이름은 부분 일치/대소문자 무시)만 적용
        """
        items = STOCK_ITEMS

        if q:
            q_str = str(q).strip()
            filtered = []
            # 코드(정수) 정확 일치 우선
            try:
                q_code = int(q_str)
            except ValueError:
                q_code = None

            for it in items:
                if q_code is not None and it.get("code") == q_code:
                    filtered.append(it)
                    continue
                name = str(it.get("name", ""))
                if q_str.lower() in name.lower():
                    filtered.append(it)
            items = filtered

        # 일관된 정렬(이름 오름차순)
        items = sorted(items, key=lambda x: str(x.get("name", "")))

        return StockItemsResponse(
            items=[
                StockItemOut(code=str(it["code"]), name=str(it["name"])) for it in items
            ]
        )

    def _compare_tool_numbers(
        self,
        nc_tools: List[Optional[int]],
        ws_tools: List[Optional[int]],
    ) -> list[str]:
        """
        NC에서 추출한 T번호 vs 워크스텝에서 유추한 T번호 비교.
        - 둘 다 숫자인 경우만 비교하며, 다르면 에러 메시지 생성.
        - 둘 중 하나라도 None이면(= 알 수 없음) 여기서는 불일치로 보지 않고,
        null 처리 여부는 _validate_project_file에서 걸러냄.
        """
        errors: list[str] = []
        for i, (n, w) in enumerate(zip(nc_tools, ws_tools), start=1):
            if n is not None and w is not None and n != w:
                errors.append(f"process[{i}]: tool number mismatch (nc={n}, ws={w})")
        return errors

    async def request_vm(self, _id: ObjectId) -> dict:
        doc = await self.dao.get(_id)
        if not doc:
            raise HTTPException(404, "vm_project not found")

        status = (doc.get("status") or "").strip()
        if status != "ready":
            raise HTTPException(
                400,
                detail={
                    "message": f"status must be 'ready' to request VM (current: {status})",
                    "validation": doc.get("validation") or {},
                },
            )

        pf_dict = self._normalize_project_file_dict(
            doc.get("project_file_draft") or {}
        )
        project_file = ProjectFileOut(**pf_dict)

        # 1) VM 시스템에 job 생성
        job_id = await self._vm_create_job(_id, project_file)

        # 2) 우리 DB에 job_id + status=running 기록
        await self.dao.set_vm_job_id(_id, job_id)
        await self.dao.set_status(_id, "running")

        return {
            "vm_project_id": str(_id),
            "vm_job_id": job_id,
            "status": "running",
        }

    async def _load_current_project_json(self, vm_project_id: ObjectId) -> dict:
        """
        latest_files['vm-project-json']가 있으면 GridFS에서 읽어 JSON 반환.
        없으면 DB draft를 기본값으로 사용.
        """
        doc = await self.dao.get(vm_project_id)
        pf_dict = self._normalize_project_file_dict(
            (doc or {}).get("project_file_draft") or {}
        )
        latest = (doc or {}).get("latest_files") or {}
        vmf_id = latest.get("vm-project-json")
        if not vmf_id:
            # 파일 아직 없으면 draft를 반환(파일 생성은 호출부에서 판단)
            return dict(pf_dict)

        vmf_doc = await self.vm_file_svc.dao.get(vmf_id)
        if not vmf_doc:
            return dict(pf_dict)

        grid_id = vmf_doc.get("gridfs_id")
        if not grid_id:
            return dict(pf_dict)

        data = await self.vm_file_svc.filestore.gfs_get_bytes(grid_id)
        try:
            return self._normalize_project_file_dict(json.loads(data.decode("utf-8")))
        except Exception:
            # 파싱 실패 시에도 draft로 폴백
            return dict(pf_dict)

    async def _write_project_json_merged(
        self,
        vm_project_id: ObjectId,
        patch: Mapping[
            str, object
        ],  # 예: {"stock_type": 45, "stock_size": "..."} 또는 {"process": [...], "process_count": 7}
    ) -> dict:
        """
        - 현재 JSON 로드 → patch 키만 덮어쓰기(부분 수정)
        - 새 JSON을 GridFS에 업로드
        - vm_file.gridfs_id 포인터만 교체(구 파일 삭제)
        - 반환: {"vm_file_id", "old_gridfs_id", "new_gridfs_id", "merged"}
        """
        # 현재 JSON 확보
        current = await self._load_current_project_json(vm_project_id)
        merged = dict(current)
        for k, v in patch.items():
            merged[k] = v

        # latest vm-project-json vm_file
        proj_doc = await self.dao.get(vm_project_id)
        latest = (proj_doc or {}).get("latest_files") or {}
        vmf_id = latest.get("vm-project-json")
        if not vmf_id:
            # 아직 파일이 없으면 새로 생성해도 되지만, 여기서는 "없다"를 명시적으로 에러 처리
            # 필요 시: self.vm_file_svc.create_from_path(...) 로 새로 만들도록 분기 가능
            raise HTTPException(400, detail="vm-project-json not found")

        vmf_doc = await self.vm_file_svc.dao.get(vmf_id)
        if not vmf_doc:
            raise HTTPException(404, detail="vm_file not found")

        old_grid = vmf_doc.get("gridfs_id")
        original_name = vmf_doc.get("original_name") or "project.prj"
        content_type = vmf_doc.get("content_type") or "application/octet-stream"

        data_bytes = json.dumps(merged, ensure_ascii=False, indent=2).encode("utf-8")

        new_grid = await self.vm_file_svc.filestore.gfs_put_bytes(
            data_bytes,
            filename=original_name,
            content_type=content_type,
            metadata={"source": "patch"},
        )

        await self.vm_file_svc.dao.update_gridfs_pointer(vmf_id, new_grid)

        # 구 파일은 정책에 따라 삭제(보관 원하면 주석)
        if old_grid:
            try:
                await self.vm_file_svc.filestore.gfs_delete(old_grid)
            except Exception:
                pass

        return {
            "vm_file_id": vmf_id,
            "old_gridfs_id": old_grid,
            "new_gridfs_id": new_grid,
            "merged": merged,
        }

    # ==========VM 호출 관련 ==========
    async def reset_to_ready(self, vm_project_id: ObjectId) -> Dict[str, Any]:
        ok = await self.dao.reset_failed_to_ready(vm_project_id)
        if not ok:
            doc = await self.dao.get(vm_project_id)
            if not doc:
                raise HTTPException(404, "vm_project not found")
            raise HTTPException(
                400,
                f"'failed' 상태에서만 리셋할 수 있습니다. 현재 상태: {doc.get('status')}",
            )
        return {"vm_project_id": str(vm_project_id), "status": "ready"}

    async def start_vm_job(
        self,
        vm_project_id: ObjectId,
        *,
        upload_mode: str = VmResultUploadMode.file.value,
    ) -> Dict[str, Any]:
        """
        1) status가 ready인지 확인 (아니면 400)
        2) 프로젝트 JSON, NC ZIP을 GridFS에서 꺼내 VM S3 업로드 API로 각각 업로드
           - query param: parent_path = proj_name (project_id는 넣지 않음)
           - 응답에서 S3 경로 문자열을 추출(없으면 에러)
        3) 토큰 발급 (username/password from settings)
        4) VM 생성 API 호출 (machine_name=eid, upload_file_link1/2 = 경로)
        5) 성공 시 vm_job_id / state / vm_last_polled_at / status=running 업데이트
           실패 시 vm_error_message만 기록하고 에러 리턴
        """
        # 0) 프로젝트 문서 조회 및 상태 확인
        doc = await self.dao.get(vm_project_id)
        if not doc:
            raise HTTPException(404, "vm_project not found")

        status = (doc.get("status") or "").strip()
        existing_job_id = doc.get("vm_job_id")

        # 이미 running 상태인 프로젝트는 재시작 불가
        if status == "running":
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "이미 VM 작업이 실행 중인 프로젝트입니다.",
                    "status": status,
                    "vm_job_id": existing_job_id,
                },
            )

        # ready인데도 vm_job_id가 남아 있으면 재시작 막기 (데이터 정합성 보호)
        if status == "ready" and existing_job_id:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "이미 VM 작업 ID가 할당된 프로젝트입니다. 재시작하려면 관리자에게 문의하세요.",
                    "status": status,
                    "vm_job_id": existing_job_id,
                },
            )

        if status != "ready":
            # needs-fix / completed / failed 등
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "status가 'ready' 상태에서만 VM 작업을 시작할 수 있습니다.",
                    "status": status,
                },
            )

        proj_name = doc.get("proj_name")
        if not proj_name:
            raise HTTPException(400, "vm_project has no proj_name")

        latest_files = doc.get("latest_files") or {}
        nc_file_id = latest_files.get("nc-split-zip")
        prj_file_id = latest_files.get("vm-project-json")
        if not nc_file_id or not prj_file_id:
            raise HTTPException(400, "vm_project has no latest vm files")
        # 1) S3 업로드: project JSON / ncdata.zip
        project_s3_path = await self._vm_upload_latest_file(
            vm_file_id=prj_file_id,
            parent_path=proj_name,
        )
        nc_s3_path = await self._vm_upload_latest_file(
            vm_file_id=nc_file_id,
            parent_path=proj_name,
        )

        # 2) 토큰 발급
        token = await self._vm_issue_token()

        # 3) VM job 생성 호출
        try:
            vm_resp = await self._vm_create_job(
                token=token,
                machine_name=str(doc.get("display_name") or doc.get("eid") or ""),
                project_s3_path=project_s3_path,
                nc_s3_path=nc_s3_path,
            )
        except HTTPException as e:
            # 생성 실패 시: 에러 메시지만 기록해두고 그대로 전파
            await self.dao.set_vm_error(
                vm_project_id,
                message=str(e.detail),
                vm_raw_status=None,
            )
            raise

        # 4) 응답에서 job_id / state 추출
        vm_job_id = self._extract_job_id(vm_resp)
        if not vm_job_id:
            # id가 없으면 우리 쪽엔 아무것도 기록하지 않고 에러
            await self.dao.set_vm_error(
                vm_project_id,
                message="VM create-job did not return id",
                vm_raw_status=vm_resp,
            )
            raise HTTPException(502, "VM create-job did not return id")

        vm_state = self._extract_state(vm_resp)

        upload_result = upload_mode != VmResultUploadMode.link.value

        # 5) DB에 job 시작 정보 기록
        await self.dao.set_vm_job_started(
            vm_project_id,
            vm_job_id=str(vm_job_id),
            vm_state=vm_state,
            upload_mode=upload_mode,
            upload_result=upload_result,
        )

        return {
            "vm_project_id": str(vm_project_id),
            "status": "running",
            "vm_job_id": str(vm_job_id),
            "vm_state": vm_state,
        }

    # ---------- 내부 유틸: VM 파일 업로드 ----------
    async def _vm_upload_latest_file(
        self,
        *,
        vm_file_id: ObjectId,
        parent_path: str,
    ) -> str:
        """
        GridFS에서 파일바이트를 읽어 VM 업로드 API로 전송.
        - Query: parent_path=<proj_name>
        - Body: multipart/form-data, file 필드
        - 응답에서 업로드된 파일 URL(경로) 문자열 추출(없으면 502)
        """

        # 1) vm_file 도큐먼트 조회
        vmf_doc = await self.vm_file_svc.dao.get(vm_file_id)
        if not vmf_doc:
            raise HTTPException(404, detail="vm_file not found")

        gridfs_id = vmf_doc.get("gridfs_id")
        if not gridfs_id:
            raise HTTPException(400, detail="vm_file has no gridfs_id")

        # 2) GridFS에서 파일 내용 로드
        content = await self.vm_file_svc.filestore.gfs_get_bytes(gridfs_id)
        filename = vmf_doc.get("original_name") or "file.bin"

        base = str(settings.VM_API_URL).rstrip("/")  # VM API 베이스 URL
        url = base + str(settings.VM_S3_UPLOAD_DETAIL)

        logger.info(
            "VM /s3-upload call: url=%s, parent_path=%s, filename=%s, size=%d",
            url,
            parent_path,
            filename,
            len(content) if content is not None else -1,
        )

        # 3) 업로드 요청 (requests 버전과 최대한 유사하게 전송)
        try:
            async with httpx.AsyncClient(timeout=180.0, http2=False) as client:
                r = await client.post(
                    url,
                    params={"parent_path": parent_path},  # project_id는 사용 안 함
                    # 🔽 requests의 `files={"file": f}` 와 최대한 비슷하게
                    files={"file": (filename, content)},
                )
        except httpx.ConnectError as e:
            # DNS 실패, 연결 실패 등
            logger.error("VM upload connect error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"VM upload connection error: {e}",
            )
        except httpx.HTTPError as e:
            # 기타 HTTP 레벨 에러
            logger.error("VM upload HTTP error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"VM upload HTTP error: {e}",
            )

        # 4) 상태 코드 확인
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(
                "VM upload failed: status=%s, text=%s",
                e.response.status_code,
                e.response.text,
            )
            raise HTTPException(
                status_code=502,
                detail=f"VM upload failed: {e.response.text}",
            )

        # 5) JSON 파싱 + 경로 추출
        data = self._safe_json(r)  # 이미 구현되어 있다고 가정
        s3_path = self._extract_s3_path(data)  # file_url 등에서 추출

        if not s3_path:
            # "리턴 값에 경로값이 제대로 오지 않았다면 에러" 요구사항
            logger.error("VM upload did not return path. response=%s", data)
            raise HTTPException(
                status_code=502,
                detail="VM upload did not return path",
            )

        logger.info("VM /s3-upload success: path=%s", s3_path)
        return s3_path

    async def _vm_issue_token(self) -> str:
        base = str(settings.VM_API_URL).rstrip("/")
        url = base + str(settings.VM_LOGIN_TOKEN)
        token_body = {
            "username": settings.VM_USERNAME,
            "password": settings.VM_PASSWORD,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, data=token_body)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(502, detail=f"VM token error: {e.response.text}")

            data = self._safe_json(r)

            # ✅ 스펙에 맞춰 깔끔하게
            access_token = data.get("access_token")
            if not access_token:
                raise HTTPException(
                    502, detail="VM token response missing access_token"
                )

            # token_type도 필요하면 같이 써도 됨 (기본 bearer)
            token_type = (data.get("token_type") or "bearer").capitalize()
            # _vm_create_job 쪽에서: headers={"Authorization": f"{token_type} {access_token}"}

            return str(access_token)

    async def _vm_create_job(
        self,
        *,
        token: str,
        machine_name: str,
        project_s3_path: str,
        nc_s3_path: str,
    ) -> Dict[str, Any]:
        base = str(settings.VM_API_URL).rstrip("/")
        # 생성 엔드포인트는 config에 선언돼 있다고 가정
        url = base + str(settings.VM_JOB_CREATE)

        body = {
            "machine_name": machine_name,
            "upload_file_link1": project_s3_path,
            "upload_file_link2": nc_s3_path,
        }
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(url, json=body, headers=headers)
            try:
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(502, detail=f"VM create error: {e.response.text}")
            return self._safe_json(r)

    def _extract_state(self, data: Any) -> Optional[str]:
        if isinstance(data, dict):
            v = data.get("state")
            if v is not None:
                return str(v)
        return None

    @staticmethod
    def _safe_json(r: httpx.Response) -> Dict[str, Any]:
        try:
            return r.json()
        except Exception:
            return {"raw": r.text}

    @staticmethod
    def _extract_s3_path(data: Dict[str, Any]) -> Optional[str]:
        """
        /s3-upload 응답에서 업로드된 파일의 URL/경로를 추출한다.

        현재 스펙:
        {
          "file_url": "https://kitech-file.s3.ap-northeast-2.amazonaws.com/...."
        }
        """
        if not isinstance(data, dict):
            return None

        candidates = [
            data.get("file_url"),  # ✅ 현재 스펙
            data.get("path"),
            data.get("s3_path"),
            data.get("url"),
            (
                (data.get("data") or {}).get("file_url")
                if isinstance(data.get("data"), dict)
                else None
            ),
            (
                (data.get("data") or {}).get("path")
                if isinstance(data.get("data"), dict)
                else None
            ),
        ]

        for c in candidates:
            if isinstance(c, str) and c.strip():
                return c.strip()
        return None

    @staticmethod
    def _extract_job_id(data: Dict[str, Any]) -> Optional[str]:
        """
        생성 응답에서 job 식별자를 관용적으로 추출:
        - data["id"] or data["_id"] or data["job_id"] or data["data"]["id"] ...
        """
        if not isinstance(data, dict):
            return None
        candidates = [
            data.get("id"),
            data.get("_id"),
            data.get("job_id"),
            (
                (data.get("data") or {}).get("id")
                if isinstance(data.get("data"), dict)
                else None
            ),
            (
                (data.get("result") or {}).get("id")
                if isinstance(data.get("result"), dict)
                else None
            ),
        ]
        for c in candidates:
            if c is None:
                continue
            return str(c)
        return None

    # =========== 풀링관련 ===========
    async def poll_all_running_once(self) -> dict:
        """
        status='running' 인 vm_project 들을 한 번씩 폴링해서
        상태를 업데이트한다.
        """
        ids = await self.dao.list_running_ids()
        results: list[dict] = []

        if not ids:
            return {"polled_count": 0, "results": []}

        # 🔽 여기에서 토큰 한 번만 발급
        try:
            token = await self._vm_issue_token()
        except HTTPException as e:
            logger.warning(
                "VM token issue failed while polling all running: %s", e.detail
            )
            # 토큰 못 받았으면 이번 라운드는 그냥 스킵
            return {
                "polled_count": 0,
                "results": [],
                "error": f"token_issue_failed: {e.detail}",
            }

        for _id in ids:
            try:
                # 🔽 토큰 재사용
                res = await self.poll_vm_status(_id, token=token)
                results.append(res)
            except HTTPException as e:
                # 개별 프로젝트 폴링 실패는 로그만 찍고 계속 진행
                logger.warning("VM poll failed for project %s: %s", str(_id), e.detail)
            except Exception as e:
                logger.exception(
                    "Unexpected error while polling project %s: %s", str(_id), e
                )

        return {
            "polled_count": len(ids),
            "results": results,
        }

    async def vm_polling_loop(self, interval_sec: int = 300) -> None:
        """
        백그라운드에서 무한 루프로 동작하면서
        일정 간격(interval_sec)마다 poll_all_running_once() 를 호출한다.
        """
        logger.info("VM polling loop started (interval=%s sec)", interval_sec)
        while True:
            try:
                await self.poll_all_running_once()
            except Exception as e:
                # 전체 루프 에러는 잡고 로그만 남긴 뒤 다음 주기로 넘어감
                logger.exception("Error in VM polling loop: %s", e)
            # 지정한 시간만큼 대기
            await asyncio.sleep(interval_sec)

    async def poll_vm_status(self, vm_project_id: ObjectId, token: str) -> dict:
        doc = await self.dao.get(vm_project_id)
        if not doc:
            raise HTTPException(404, "vm_project not found")

        job_id = doc.get("vm_job_id")
        if not job_id:
            raise HTTPException(400, "vm_job_id is empty")

        # VM API URL 구성
        base = str(settings.VM_API_URL).rstrip("/")
        url = base + settings.VM_GET_JOB_DETAIL_PATH.format(macsim_id=job_id)

        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                r = await client.get(url, headers=headers)
                r.raise_for_status()
            except httpx.HTTPError as e:
                msg = getattr(e.response, "text", str(e))
                await self.dao.set_vm_poll_result(
                    vm_project_id,
                    status=doc.get("status", "running"),
                    vm_state=doc.get("vm_raw_status"),
                    vm_error_message=f"VM poll error: {msg}",
                )
                raise HTTPException(502, detail=f"VM poll error: {msg}")

        resp = self._safe_json(r)
        vm_state = self._extract_state(resp)  # 응답 구조가 달라져도 한 곳에서 처리

        # ===== 상태 분기 =====
        if vm_state in ("WAIT", "RUN", "UPLOADING"):
            # 아직 진행 중 → 계속 running 으로 유지
            new_status = "running"

        elif vm_state == "COMPLETE":
            # VM 결과 ZIP 링크
            result_link = resp.get("download_file_link")

            if not result_link:
                await self.dao.set_vm_poll_result(
                    vm_project_id,
                    status="failed",
                    vm_state="ERROR",
                    vm_error_message="VM returned COMPLETE but no download_file_link",
                )
                return {
                    "vm_project_id": str(vm_project_id),
                    "status": "failed",
                    "vm_state": "ERROR",
                }

            upload_mode = self._resolve_upload_mode_from_doc(doc)

            if upload_mode == VmResultUploadMode.json.value:
                try:
                    await self._create_and_upload_vm_json_dt_files(
                        vm_project_id, doc, result_link
                    )
                    new_status = "completed"
                except Exception as upload_err:
                    err_msg = f"VM JSON dt_file 업로드 실패: {upload_err}"
                    logger.error(
                        "json dt_file upload failed: project=%s err=%s",
                        str(vm_project_id),
                        upload_err,
                    )
                    latest_doc = await self.dao.get(vm_project_id)
                    upload_info = dict(
                        (latest_doc or {}).get("vm_result_upload")
                        or self._empty_vm_result_upload(upload_mode)
                    )
                    upload_info["error_message"] = err_msg
                    upload_info["updated_at"] = datetime.now().isoformat()
                    await self.dao.set_vm_result_upload(
                        vm_project_id,
                        upload_info=upload_info,
                        project_status="failed",
                        vm_raw_status=vm_state,
                        vm_error_message=err_msg,
                    )
                    return {
                        "vm_project_id": str(vm_project_id),
                        "status": "failed",
                        "vm_state": vm_state,
                    }
            else:
                _MAX_DT_FILE_ATTEMPTS = 3
                current_attempts = (doc.get("vm_dt_file_upload_attempts") or 0) + 1
                try:
                    await self._create_and_upload_vm_dt_file(doc, result_link)
                    new_status = "completed"
                except Exception as upload_err:
                    if current_attempts >= _MAX_DT_FILE_ATTEMPTS:
                        err_msg = f"VM dt_file 플랫폼 업로드 실패 ({current_attempts}/{_MAX_DT_FILE_ATTEMPTS}회 시도): {upload_err}"
                        logger.error("dt_file upload max retries exceeded: project=%s err=%s", str(vm_project_id), upload_err)
                        await self.dao.set_vm_poll_result(
                            vm_project_id,
                            status="failed",
                            vm_state=vm_state,
                            vm_error_message=err_msg,
                        )
                        return {
                            "vm_project_id": str(vm_project_id),
                            "status": "failed",
                            "vm_state": vm_state,
                        }
                    else:
                        err_msg = f"VM dt_file 업로드 시도 {current_attempts}/{_MAX_DT_FILE_ATTEMPTS} 실패: {upload_err}"
                        logger.warning("dt_file upload attempt %d failed: project=%s err=%s", current_attempts, str(vm_project_id), upload_err)
                        await self.dao.set_dt_file_upload_failed(
                            vm_project_id,
                            attempts=current_attempts,
                            message=err_msg,
                            vm_raw_status=vm_state,
                        )
                        return {
                            "vm_project_id": str(vm_project_id),
                            "status": "running",
                            "vm_state": vm_state,
                        }

        elif "ERR" in (vm_state or "").upper():
            # ERROR, ERROR-AppsPro Down, ERROR-ERR-UNKNOWN, ERR-xxx 등 ERR 포함 전부 failed 처리
            new_status = "failed"
            await self.dao.set_vm_poll_result(
                vm_project_id,
                status=new_status,
                vm_state=vm_state,
                vm_error_message=vm_state,
            )
            logger.warning("VM job failed: project=%s vm_state=%s", str(vm_project_id), vm_state)
            return {
                "vm_project_id": str(vm_project_id),
                "status": new_status,
                "vm_state": vm_state,
            }

        else:
            # 알 수 없는 상태값 → running 유지하고 경고만 기록
            logger.warning(
                "Unknown VM state '%s' for project %s; keep running",
                vm_state,
                str(vm_project_id),
            )
            new_status = "running"

        # 공통: VM 상태/에러 갱신
        await self.dao.set_vm_poll_result(
            vm_project_id,
            status=new_status,
            vm_state=vm_state,
            vm_error_message=None if new_status != "failed" else vm_state,
        )

        return {
            "vm_project_id": str(vm_project_id),
            "status": new_status,
            "vm_state": vm_state,
        }

    async def _compute_next_vm_seq_id(
        self,
        *,
        gid: str,
        aid: str,
        eid: str,
        wpid: Optional[str],
        source: str = "iso",
    ) -> int:
        """
        동일한 (gid, aid, eid, wpid) 조합으로 이미 등록된 VM dt_file 들을 조회해서
        SEQ_ID 최댓값 + 1 을 반환한다. 없으면 1부터 시작.
        source="dp" 이면 DP API로 조회, 그 외엔 ISO API.
        """
        max_seq = 0

        if source == "dp":
            try:
                result = await dp_client.list_elements_by_gid(gid)
                candidates = [
                    item for item in (result.get("content") or [])
                    if (item.get("type") or "").lower() == "file"
                ]
            except Exception:
                candidates = []

            for item in candidates:
                item_aid = item.get("assetId") or ""
                item_eid = item.get("elementId") or ""
                if not item_aid or not item_eid:
                    continue
                try:
                    xml = await dp_client.get_element_xml(aid=item_aid, eid=item_eid)
                except Exception:
                    continue
                if not xml:
                    continue
                info = parse_dt_file_xml(xml) or {}
                if str(info.get("category") or "").strip().upper() != "VM":
                    continue
                # DP: DT_GLOBAL_ASSET + DT_PROJECT + WORKPLAN으로 매칭 (DT_ASSET 스킵)
                refs = info.get("refs") or {}
                if (refs.get("DT_GLOBAL_ASSET") or "") != gid:
                    continue
                if (refs.get("DT_PROJECT") or "") != eid:
                    continue
                if wpid and (refs.get("WORKPLAN") or "") != wpid:
                    continue
                for p in (info.get("properties") or []):
                    if not isinstance(p, dict):
                        continue
                    if str(p.get("key") or "").strip() != "SEQ_ID":
                        continue
                    try:
                        v = int(str(p.get("value") or "").strip())
                    except ValueError:
                        v = None
                    if v is not None and v > max_seq:
                        max_seq = v
                    break
        else:
            pairs = await self._list_dtfile_pairs(gid=gid)
            for aid_try, eid_try in pairs:
                try:
                    xml = await self._fetch_dt_file_xml(eid=eid_try, gid=gid, aid=aid_try)
                except Exception:
                    continue
                if not xml:
                    continue
                info = parse_dt_file_xml(xml) or {}
                if str(info.get("category") or "").strip().upper() != "VM":
                    continue
                if not match_dt_file_refs(info, gid=gid, aid=aid, eid=eid, wpid=wpid):
                    continue
                for p in (info.get("properties") or []):
                    if not isinstance(p, dict):
                        continue
                    if str(p.get("key") or "").strip() != "SEQ_ID":
                        continue
                    try:
                        v = int(str(p.get("value") or "").strip())
                    except ValueError:
                        v = None
                    if v is not None and v > max_seq:
                        max_seq = v
                    break

        return max_seq + 1 if max_seq > 0 else 1

    async def _iso_register_vm_dt_file(
        self,
        *,
        gid: str,
        vm_aid: str,
        vm_eid: str,
        xml_str: str,
        upload_file_path: Optional[str] = None,
        upload_file_name: Optional[str] = None,
        upload_content_type: str = "application/octet-stream",
    ) -> Dict[str, Any]:
        """
        VM 결과 dt_file(XML)을 ISO에 등록.

        ISO 스펙:
        - POST /api/v3/assets
        - multipart/form-data
          - xml: 업로드할 dt_asset XML (여러 dt_elements 포함 가능)
          - upload_files: dt_file 요소들과 매칭되는 실제 파일들 (여러 개 가능, VM 결과는 링크만 쓰므로 비워둬도 됨)

        여기서는:
        - dt_asset 내에 우리가 만든 dt_file 이 이미 포함되어 있으므로
          xml 파트만 파일처럼 올린다.
        - VM 결과 ZIP 자체는 ISO에 직접 업로드하지 않고,
          dt_file.path 에 S3 링크를 넣는 구조이므로 upload_files 는 보내지 않는다.
        """
        base = str(settings.ISO_API_URL).rstrip("/")
        url = base + str(settings.ISO_PATH_ASSET_LIST)  # 예: "/api/v3/assets"

        xml_bytes = xml_str.encode("utf-8")

        # httpx 의 files 인자를 사용하면 multipart/form-data 로 전송된다.
        # 필드 이름은 Swagger 에 나온 대로 "xml" 이어야 함.
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                if upload_file_path:
                    file_name = upload_file_name or os.path.basename(upload_file_path)
                    with open(upload_file_path, "rb") as fh:
                        files = [
                            ("xml", ("vm_dt_file.xml", xml_bytes, "application/xml")),
                            (
                                "upload_files",
                                (file_name, fh, upload_content_type),
                            ),
                        ]
                        r = await client.post(url, files=files)
                else:
                    files = {
                        "xml": ("vm_dt_file.xml", xml_bytes, "application/xml"),
                    }
                    r = await client.post(url, files=files)
                r.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=502,
                    detail=f"ISO vm dt_file create error: {e.response.text}",
                )

        return self._safe_json(r)

    @staticmethod
    async def _stream_download_to_tempfile(url: str) -> str:
        """
        URL에서 파일을 스트리밍으로 다운로드해 임시 파일 경로를 반환한다.
        호출자가 사용 후 반드시 삭제해야 한다.
        """
        import tempfile
        suffix = "." + (url.rstrip("/").split("/")[-1].split(".")[-1] or "zip")
        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        async with httpx.AsyncClient(timeout=600.0) as client:
            async with client.stream("GET", url) as r:
                r.raise_for_status()
                with open(tmp_path, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=4 * 1024 * 1024):
                        f.write(chunk)
        return tmp_path

    async def _dp_register_vm_dt_file(
        self,
        *,
        xml_str: str,
        download_url: Optional[str] = None,
        file_path: Optional[str] = None,
        file_name: Optional[str] = None,
        content_type: str = "application/zip",
    ) -> Any:
        """
        DP에 VM 결과 dt_file 등록.

        download_url이 있으면 파일을 스트리밍 다운로드 후 DP에 파일+XML 함께 업로드.
        download_url이 None이면 XML(링크 포함)만 업로드.
        임시 파일은 finally에서 반드시 삭제한다.
        """
        if download_url is None and file_path is None:
            # 파일 첨부 없이 XML(링크)만 등록 → /asset/xml 사용
            # /asset/xml-with-file 은 파일 첨부가 없으면 서버에서 400 반환
            try:
                return await dp_client.upload_xml(xml_str)
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"DP vm dt_file 등록 실패: {e}")

        tmp_path = None
        try:
            target_path = file_path
            if target_path is None:
                tmp_path = await self._stream_download_to_tempfile(download_url)
                target_path = tmp_path
                logger.info("VM 결과 임시 저장 완료: %s (%d bytes)", tmp_path, os.path.getsize(tmp_path))

            upload_name = file_name
            if not upload_name:
                if download_url:
                    upload_name = download_url.rstrip("/").split("/")[-1] or "vm_result.zip"
                else:
                    upload_name = os.path.basename(target_path) or "vm_result.bin"

            return await dp_client.upload_xml_with_file(
                xml_str,
                file_path=target_path,
                file_name=upload_name,
                content_type=content_type,
            )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"DP vm dt_file 등록 실패: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
                logger.info("VM 결과 임시 파일 삭제: %s", tmp_path)

    async def _load_or_rebuild_process_annotations(self, doc: dict) -> list[dict]:
        items = doc.get("process_annotations") or []
        if items:
            return items
        rebuilt = await self._rebuild_process_annotations_from_source(doc)
        if rebuilt and doc.get("_id"):
            await self.dao.update_process_annotations(doc["_id"], rebuilt)
        return rebuilt

    def _collect_vm_json_upload_items(
        self,
        *,
        extract_root: str,
        project_file: dict[str, Any],
        process_annotations: list[dict],
        seq_id: int,
    ) -> list[dict[str, Any]]:
        processes = project_file.get("process") or []
        if len(processes) != len(process_annotations):
            raise ValueError(
                f"process 수({len(processes)})와 process annotation 수({len(process_annotations)})가 일치하지 않습니다."
            )

        items: list[dict[str, Any]] = []
        for idx, process in enumerate(processes, start=1):
            rel_dir = str(process.get("output_dir_path") or "").strip()
            if not rel_dir:
                raise ValueError(f"process {idx} output_dir_path가 비어 있습니다.")

            annotation = process_annotations[idx - 1] or {}
            workingstep_id = str(annotation.get("workingstep_id") or "").strip()
            if not workingstep_id:
                raise ValueError(f"process {idx} workingstep_id가 비어 있습니다.")

            rel_dir_os = os.path.normpath(rel_dir.replace("\\", os.sep).replace("/", os.sep))
            abs_dir = os.path.normpath(os.path.join(extract_root, rel_dir_os))
            if not os.path.isdir(abs_dir):
                raise ValueError(f"process {idx} 결과 폴더를 찾지 못했습니다: {rel_dir}")

            json_paths: list[str] = []
            for root, _, files in os.walk(abs_dir):
                for name in files:
                    if name.lower().endswith(".json"):
                        json_paths.append(os.path.join(root, name))

            if len(json_paths) != 1:
                raise ValueError(
                    f"process {idx} 결과 JSON 파일은 정확히 1개여야 합니다. 현재 {len(json_paths)}개"
                )

            element_id = f"vm_json_{seq_id:03d}_{idx:03d}"
            json_path = json_paths[0]
            items.append(
                {
                    "process_index": idx,
                    "workingstep_id": workingstep_id,
                    "element_id": element_id,
                    "file_path": json_path,
                    "file_name": os.path.basename(json_path),
                }
            )

        return items

    async def _create_and_upload_vm_json_dt_files(
        self,
        vm_project_id: ObjectId,
        vm_project_doc: dict,
        download_link: str,
    ) -> None:
        gid = vm_project_doc.get("gid")
        aid = vm_project_doc.get("aid")
        eid = vm_project_doc.get("eid")
        wpid = vm_project_doc.get("wpid")
        source = vm_project_doc.get("source") or "iso"

        if not (gid and aid and eid):
            raise HTTPException(
                status_code=400,
                detail="vm_project has no gid/aid/eid for vm json dt_file",
            )

        process_annotations = await self._load_or_rebuild_process_annotations(vm_project_doc)
        project_file = self._normalize_project_file_dict(
            vm_project_doc.get("project_file_draft") or {}
        )

        with tempfile.TemporaryDirectory(prefix="vm-json-result-") as extract_root:
            zip_path = await self._stream_download_to_tempfile(download_link)
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(extract_root)
            finally:
                if os.path.exists(zip_path):
                    os.remove(zip_path)

            seq_id = await self._compute_next_vm_seq_id(
                gid=gid,
                aid=aid,
                eid=eid,
                wpid=wpid,
                source=source,
            )
            upload_items = self._collect_vm_json_upload_items(
                extract_root=extract_root,
                project_file=project_file,
                process_annotations=process_annotations,
                seq_id=seq_id,
            )

            upload_info = self._empty_vm_result_upload(VmResultUploadMode.json.value)
            upload_info["seq_id"] = seq_id
            upload_info["total_count"] = len(upload_items)
            upload_info["updated_at"] = datetime.now().isoformat()
            await self.dao.set_vm_result_upload(vm_project_id, upload_info=upload_info)

            for item in upload_items:
                xml_str = make_vm_dt_file_xml(
                    asset_global_id=gid,
                    vm_asset_id=item["element_id"],
                    vm_element_id=item["element_id"],
                    display_name=item["file_name"],
                    element_description="vm result json file.",
                    content_type="application/json",
                    download_file_link="",
                    gid=gid,
                    aid=aid,
                    eid=eid,
                    wpid=wpid,
                    workingstep_id=item["workingstep_id"],
                    process_index=item["process_index"],
                    seq_id=seq_id,
                )

                try:
                    if source == "dp":
                        await self._dp_register_vm_dt_file(
                            xml_str=xml_str,
                            file_path=item["file_path"],
                            file_name=item["file_name"],
                            content_type="application/json",
                        )
                    else:
                        await self._iso_register_vm_dt_file(
                            gid=gid,
                            vm_aid=item["element_id"],
                            vm_eid=item["element_id"],
                            xml_str=xml_str,
                            upload_file_path=item["file_path"],
                            upload_file_name=item["file_name"],
                            upload_content_type="application/json",
                        )
                except Exception as exc:
                    upload_info["failed_index"] = item["process_index"]
                    upload_info["error_message"] = (
                        f"process {item['process_index']} ({item['element_id']}) 업로드 실패: {exc}"
                    )
                    upload_info["updated_at"] = datetime.now().isoformat()
                    await self.dao.set_vm_result_upload(
                        vm_project_id,
                        upload_info=upload_info,
                        project_status="failed",
                        vm_raw_status="COMPLETE",
                        vm_error_message=upload_info["error_message"],
                    )
                    raise HTTPException(status_code=502, detail=upload_info["error_message"])

                upload_info["uploaded_indices"].append(item["process_index"])
                upload_info["uploaded_element_ids"].append(item["element_id"])
                upload_info["last_uploaded_index"] = item["process_index"]
                upload_info["last_uploaded_element_id"] = item["element_id"]
                upload_info["updated_at"] = datetime.now().isoformat()
                await self.dao.set_vm_result_upload(
                    vm_project_id,
                    upload_info=upload_info,
                )

    async def _create_and_upload_vm_dt_file(
        self,
        vm_project_doc: dict,
        download_link: str,
    ) -> None:
        """
        VM에서 COMPLETE + download_file_link 가 온 경우:
        1) 기존 VM dt_file 들을 보고 다음 SEQ_ID 계산
        2) vm_aid / vm_eid 규칙(vm_001, vm_002...) 결정
        3) make_vm_dt_file_xml 로 XML 생성
        4) source에 따라 ISO 또는 DP에 dt_file 등록
        """
        gid = vm_project_doc.get("gid")
        aid = vm_project_doc.get("aid")
        eid = vm_project_doc.get("eid")
        wpid = vm_project_doc.get("wpid")
        source = vm_project_doc.get("source") or "iso"
        upload_mode = self._resolve_upload_mode_from_doc(vm_project_doc)
        upload_result = upload_mode != VmResultUploadMode.link.value

        if not (gid and aid and eid):
            raise HTTPException(
                status_code=400,
                detail="vm_project has no gid/aid/eid for vm dt_file",
            )

        # 1) 기존 VM dt_file 들에서 SEQ_ID 최댓값 + 1 계산 (source에 따라 조회 API 분기)
        seq_id = await self._compute_next_vm_seq_id(
            gid=gid,
            aid=aid,
            eid=eid,
            wpid=wpid,
            source=source,
        )

        # 2) vm aid/eid 규칙: vm_001, vm_002 ... (SEQ_ID와 통일)
        vm_aid = f"vm_{seq_id:03d}"
        vm_eid = vm_aid

        # 3) XML 생성
        # upload_result=True: 파일 직접 업로드 → <path>는 빈값 (플랫폼이 자동 채움)
        # upload_result=False: 링크만 저장 → <path>에 download_link 삽입
        xml_str = make_vm_dt_file_xml(
            asset_global_id=gid,
            vm_asset_id=vm_aid,
            download_file_link="" if upload_result else download_link,
            gid=gid,
            aid=aid,
            eid=eid,
            wpid=wpid,
            seq_id=seq_id,
        )

        # 4) 등록
        if source == "dp":
            if upload_result:
                # 파일 다운로드 후 DP에 직접 업로드
                await self._dp_register_vm_dt_file(xml_str=xml_str, download_url=download_link)
            else:
                # 링크만 XML에 넣어 DP에 등록
                await self._dp_register_vm_dt_file(xml_str=xml_str, download_url=None)
            logger.info(
                "DP vm dt_file registered: gid=%s vm_aid=%s seq_id=%d upload_mode=%s",
                gid, vm_aid, seq_id, upload_mode,
            )
        else:
            await self._iso_register_vm_dt_file(gid=gid, vm_aid=vm_aid, vm_eid=vm_eid, xml_str=xml_str)
            logger.info(
                "ISO vm dt_file registered: gid=%s vm_aid=%s seq_id=%d upload_mode=%s",
                gid, vm_aid, seq_id, upload_mode,
            )
