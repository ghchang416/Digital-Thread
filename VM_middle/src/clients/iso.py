# src/clients/iso.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
from src.core.config import settings
from src.clients.http import HttpClient

from src.utils.xml_parser import extract_project_summary

_iso = HttpClient(
    settings.ISO_API_URL,
    timeout=settings.HTTP_TIMEOUT_SEC,
    retries=settings.HTTP_RETRIES,
)


# ---------------- 내부 유틸 ----------------


def _normalize_gaids(raw: Any) -> List[str]:
    """
    다양한 응답 포맷에서 글로벌 에셋 id 들만 중복제거하여 리스트로 뽑는다.
    """
    if isinstance(raw, dict):
        arr = raw.get("global_asset_ids") or raw.get("items") or raw.get("ids") or []
    elif isinstance(raw, list):
        arr = raw
    else:
        arr = []
    seen, out = set(), []
    for x in arr:
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _mk_gid_map(
    item: Dict[str, Any], gid_fallback: Optional[str] = None
) -> Dict[str, Any]:
    """
    ISO 응답(dict)에서 gid/aid/eid로 필드를 통일해서 리턴.
    알려진 키(global_asset_id/asset_id/element_id)가 없으면 fallback(gid_fallback)을 사용.
    - 원본 보존이 필요하면 caller가 따로 저장(meta 등에)하면 됨.
    """
    gid = str(item.get("global_asset_id") or gid_fallback or "").strip()
    aid = str(item.get("asset_id") or "").strip()
    eid = str(item.get("element_id") or "").strip()
    out = dict(item)  # 기타 필드 유지
    out["gid"] = gid
    out["aid"] = aid
    out["eid"] = eid
    # 깔끔하게: 원래 키를 꼭 지울 필요는 없지만, 혼선 방지 위해 제거 권장
    out.pop("global_asset_id", None)
    out.pop("asset_id", None)
    out.pop("element_id", None)
    return out


# ---------------- 글로벌/프로젝트 리스트 ----------------


async def list_global_asset_ids() -> List[str]:
    """
    GET /api/v3/globals
    """
    data = await _iso.get_json(settings.ISO_PATH_GLOBALS)
    return _normalize_gaids(data)


async def list_projects_by_gid(gid: str) -> List[Dict[str, Any]]:
    """
    GET /api/v3/projects?global_asset_id={gid}
    반환 아이템에 gid/aid/eid 통일 키를 심어 반환.
    """
    data = await _iso.get_json(
        settings.ISO_PATH_PROJECTS,
        params={"global_asset_id": gid},
    )
    if isinstance(data, dict):
        items = data.get("items") or data.get("projects") or data.get("assets") or []
    elif isinstance(data, list):
        items = data
    else:
        items = []

    out: List[Dict[str, Any]] = []
    for p in items:
        if not isinstance(p, dict):
            continue
        out.append(_mk_gid_map(p, gid_fallback=gid))
    return out


async def list_projects(
    gid: Optional[str] = None,
    *,
    gid_limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    gid가 주어지면 해당 gid의 프로젝트, 없으면 상위 N개의 gid에 대해 라운드-로빈으로 수집.
    """
    if gid:
        return await list_projects_by_gid(gid)
    gids = (await list_global_asset_ids())[:gid_limit]
    results: List[Dict[str, Any]] = []
    for g in gids:
        results.extend(await list_projects_by_gid(g))
    return results


# ---------------- 에셋 리스트/디테일 ----------------


async def list_assets_by_gid(
    gid: str,
    *,
    type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    GET /api/v3/assets?global_asset_id={gid}[&type=...]
    응답 아이템들에 gid/aid/eid를 통일 키로 추가하여 반환.
    """
    q = {"global_asset_id": gid}
    if type:
        q["type"] = type
    data = await _iso.get_json(settings.ISO_PATH_ASSET_LIST, params=q)
    items = []
    if isinstance(data, dict):
        items = data.get("assets") or data.get("items") or data.get("data") or []
    elif isinstance(data, list):
        items = data

    out: List[Dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        out.append(_mk_gid_map(it, gid_fallback=gid))
    return out


async def list_dtfile_pairs(gid: str) -> List[Tuple[str, str]]:
    """
    dt_file 전용 간편 페어: [(aid, eid), ...]
    (aid는 nc_asset 같은 에셋 아이디, eid는 개별 dt_file element id)
    """
    assets = await list_assets_by_gid(gid, type="dt_file")
    pairs: List[Tuple[str, str]] = []
    for a in assets:
        aid = (a.get("aid") or "").strip()
        eid = (a.get("eid") or "").strip()
        if aid and eid:
            pairs.append((aid, eid))
    return pairs


async def get_project_detail(
    eid: str,
    *,
    gid: str,
    aid: str,
) -> Dict[str, Any]:
    """
    GET /api/v3/projects/{eid}?global_asset_id={gid}&asset_id={aid}
    응답 본문은 그대로 반환하되, caller에서 data["data"]로 XML 텍스트를 사용.
    """
    path = settings.ISO_PATH_PROJECT_DETAIL.format(element_id=eid)
    params = {"global_asset_id": gid, "asset_id": aid}
    return await _iso.get_json(path, params=params)


async def get_asset_detail(
    eid: str,
    *,
    gid: str,
    aid: str,
    type: str = "dt_material",
) -> Dict[str, Any]:
    """
    GET /api/v3/assets/{eid}?global_asset_id={gid}&asset_id={aid}&type={type}
    (dt_file, dt_material, dt_cutting_tool_13399 등)
    """
    path = settings.ISO_PATH_ASSET_DETAIL.format(element_id=eid)
    params = {"global_asset_id": gid, "asset_id": aid, "type": type}
    return await _iso.get_json(path, params=params)


async def list_projects_with_summary(
    gid: Optional[str] = None,
    *,
    gid_limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    list_projects()에서 받은 (gid, aid, eid) 목록에
    dt_project XML을 붙여서 summary까지 생성한 확장된 리스트.
    """
    rows = await list_projects(gid=gid, gid_limit=gid_limit)

    enriched = []

    for r in rows:
        gid_v = r["gid"]
        aid_v = r["aid"]
        eid_v = r["eid"]

        try:
            # 1) dt_project XML detail 호출
            detail = await get_project_detail(
                eid=eid_v,
                gid=gid_v,
                aid=aid_v,
            )
            xml_text = detail.get("data") or ""
        except Exception:
            # detail 불러오기 실패 → fallback
            enriched.append({**r})
            continue

        # 2) XML에서 summary 추출
        summary = extract_project_summary(xml_text)

        # 3) row에 병합
        enriched.append(
            {
                **r,
                "description": summary.get("description"),
                "name": summary.get("name") or r.get("name"),
                "main_wpid": summary.get("main_wpid"),
                "workplan_ids": summary.get("workplan_ids"),
            }
        )

    return enriched
