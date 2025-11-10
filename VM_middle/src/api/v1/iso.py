# src/api/v1/iso.py
from __future__ import annotations
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from src.clients.iso import list_projects_by_gid, list_projects
from src.schemas.iso import ProjectRow, ProjectListResp  # ProjectRow: gid/aid/eid 필수

router = APIRouter(prefix="/iso-projects", tags=["iso"])


@router.get(
    "",
    response_model=ProjectListResp,
    response_model_exclude_none=True,
)
async def get_projects(
    gid: Optional[str] = Query(None, description="Global Asset ID (URL)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    gid_limit: int = Query(20, ge=1, le=1000),
):
    """
    ISO 프로젝트 리스트.
    - 입력은 gid(옵션). 없으면 상위 gid들을 라운드로빈 수집.
    - 출력은 gid/aid/eid 로 통일된 스키마(ProjectRow).
    """
    try:
        raw = await (
            list_projects_by_gid(gid)
            if gid
            else list_projects(gid=None, gid_limit=gid_limit)
        )
    except Exception as e:
        # upstream 문제를 502로 래핑
        raise HTTPException(status_code=502, detail=f"ISO upstream error: {e}")

    total = len(raw)
    sliced = raw[offset : offset + limit]
    has_more = (offset + limit) < total
    next_offset = (offset + limit) if has_more else None

    items: List[ProjectRow] = []
    missing_count = 0

    for r in sliced:
        if not isinstance(r, dict):
            continue
        gid_v = r.get("gid")
        aid_v = r.get("aid")
        eid_v = r.get("eid")
        if not (gid_v and aid_v and eid_v):
            # 정규화 실패(레거시 섞였거나 불완전 응답) → 스킵
            missing_count += 1
            continue

        items.append(
            ProjectRow(
                gid=gid_v,
                aid=aid_v,
                eid=eid_v,
                name=r.get("name") or r.get("display_name") or r.get("title"),
                type=r.get("type"),
            )
        )

    # (선택) 일부가 스킵됐다면 경고 헤더를 달 수도 있지만 여기선 본문만 반환
    return ProjectListResp(
        items=items, has_more=has_more, next_offset=next_offset, total=total
    )
