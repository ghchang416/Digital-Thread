# src/services/vm_project.py
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import shutil
import json

import httpx
from bson import ObjectId
from fastapi import HTTPException

from src.core.config import settings
from src.dao.vm_project import VmProjectDAO
from src.schemas.vm_project import (
    ProcessItemIn,
    ProcessPatchIn,
    ProjectFileOut,
    StockInfo,
    StockPatchIn,
    VmProjectCreateIn,
    VmProjectListResponse,
    VmProjectListItem,
    VmProjectDetailOut,
    StockItemOut,
    StockItemsResponse,
)
from src.utils.nc_splitter import (
    extract_tool_numbers_from_paths,  # ([saved_paths]) -> List[int|None]
    process_nc_text,  # (nc_text: str, output_dir: str, base_filename_with_ext: str) -> List[str]
)
from src.utils.stock import lookup_stock_code
from src.utils.xml_parser import (
    extract_material_ref_from_project_xml,  # -> Optional[(gid, aid, eid)]
    extract_tool_refs_in_order,  # (project_xml, wpid) -> [{gid, aid, eid, tool_element_id, ...}]
    match_dt_file_refs,  # (parsed, gid=..., aid=..., eid=..., wpid=...)
    parse_cutting_tool_13399_xml,
    parse_dt_file_xml,
    parse_material_xml,
)
from src.services.vm_file import VmFileService
from src.utils.stock import STOCK_ITEMS

# ---------------- 내부 유틸 (정규식) ----------------
_COORD_RE = re.compile(r"\b([xyz])\s+coordinates_mm\s*:\s*([+-]?\d+(?:\.\d+)?)", re.I)
_MIN_RE = re.compile(r"\bmin_([xyz])\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_MAX_RE = re.compile(r"\bmax_([xyz])\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)
_LEN_RE = re.compile(r"\b([xyz])\s*length_mm\s*[:=]\s*([+-]?\d+(?:\.\d+)?)", re.I)

_STOCK_SIZE_6NUM_RE = re.compile(
    r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*"
    r"-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$"
)


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
    stock_size = f"{x_min},{y_min},{z_min},{x_max},{y_max},{z_max}"
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
    async def compute_stock_auto(self, payload: VmProjectCreateIn) -> StockInfo:
        # payload: gid, aid, eid, wpid  (스키마가 개정되었다고 가정)
        proj_xml = await self._fetch_project_xml(
            eid=payload.eid, gid=payload.gid, aid=payload.aid
        )

        mat_ref = extract_material_ref_from_project_xml(
            proj_xml
        )  # -> (gid2, aid2, eid2) | None
        if mat_ref:
            gid2, aid2, eid2 = mat_ref
            gid2 = gid2 or payload.gid
            aid2 = aid2 or payload.aid
            mxml = await self._fetch_material_xml(eid=eid2, gid=gid2, aid=aid2)
            if mxml:
                return _stock_from_material_xml(mxml)

        return StockInfo(
            stock_type=None,
            stock_size=None,
            reason="material 추정 실패(its_workpieces/ref_dt_material 단서 없음)",
        )

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

    async def get_project_file(self, _id: ObjectId) -> ProjectFileOut:
        doc = await self.dao.get(_id)
        pf = (doc or {}).get("project_file_draft") or {}
        return ProjectFileOut(**pf)

    async def patch_stock(self, _id: ObjectId, patch: StockPatchIn) -> ProjectFileOut:
        doc = await self.dao.get(_id)
        pf = (doc or {}).get("project_file_draft") or {}
        if patch.stock_type is not None:
            pf["stock_type"] = patch.stock_type
        if patch.stock_size is not None:
            pf["stock_size"] = patch.stock_size
        await self.dao.update_project_file_draft(_id, pf)
        return ProjectFileOut(**pf)

    async def patch_process(
        self, _id: ObjectId, patch: ProcessPatchIn
    ) -> ProjectFileOut:
        doc = await self.dao.get(_id)
        pf = (doc or {}).get("project_file_draft") or {}
        pf["process"] = [p.model_dump() for p in patch.process]
        pf["process_count"] = len(patch.process)
        await self.dao.update_project_file_draft(_id, pf)
        return ProjectFileOut(**pf)

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

        # 2) 워크플랜 확인/WS 추출
        ws_refs = extract_tool_refs_in_order(
            proj_xml, wpid=payload.wpid
        )  # [{gid, aid, eid, tool_element_id, ...}]
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
                return "{:.6f}".format(x) if isinstance(x, (int, float)) else "null"

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

        # 11) ncdata.zip
        zip_out = os.path.join(work_dir, "ncdata")
        archive_path = shutil.make_archive(
            zip_out, "zip", root_dir=work_dir, base_dir="ncdata"
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
        """
        # 1) 파일 생성 단계
        stock, project_file, debug = await self.preview_from_iso_with_nc(payload)
        zip_path = debug["ncdata_zip"]  # tmp/<proj>/ncdata.zip
        prj_path = debug["project_prj"]  # tmp/<proj>/<eid>[ -N].prj
        proj_name = debug.get("proj_name")
        dtfile_meta = debug.get("dt_file") or {}

        # 2) vm_project 생성 (초기)
        vm_project_id = await self.dao.insert_initial_from_iso(
            source="iso",
            gid=payload.gid,
            aid=payload.aid,
            eid=payload.eid,
            wpid=payload.wpid,
            project_file_draft=project_file.model_dump(),
            proj_name=proj_name,
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
            content_type="application/json",
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

    def _validate_project_file(self, pf: ProjectFileOut) -> list[str]:
        errors: list[str] = []

        # stock
        if not pf.stock_type:
            errors.append("stock_type is empty")
        if not pf.stock_size or not _STOCK_SIZE_6NUM_RE.match(pf.stock_size):
            errors.append("stock_size must be 6 numbers separated by commas")

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
                    proj_name=d.get("proj_name"),
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

        pf_dict = doc.get("project_file_draft") or {}
        # ProjectFileOut 생성(빈값도 안전하게)
        project_file = ProjectFileOut(**pf_dict)

        return VmProjectDetailOut(
            id=str(doc.get("_id")),
            status=doc.get("status"),
            proj_name=doc.get("proj_name"),
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
        )

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
                StockItemOut(code=int(it["code"]), name=str(it["name"])) for it in items
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
