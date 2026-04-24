# src/api/v1/dp.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from src.schemas.vm_project import (
    DpProjectListResponse,
    DpProjectItem,
    DpWorkplanListResponse,
    DpWorkplanItem,
)
from src.services.vm_project import VmProjectService
from src.database import get_vm_project_service
import src.clients.dp as dp_client
from src.utils.xml_parser import extract_vm_workplans

router = APIRouter(prefix="/dp", tags=["dp"])


@router.get("/projects", response_model=DpProjectListResponse)
async def list_dp_projects(
    page: int = Query(0, ge=0, description="페이지 (0-base)"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    q: str | None = Query(None, description="DP 프로젝트 검색어 (allSearch)"),
):
    """
    DP에 등록된 프로젝트 목록을 조회합니다.
    """
    try:
        data = await dp_client.list_projects(page=page, size=size, all_search=q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DP API 호출 실패: {e}")

    content = data.get("content") or []
    total = data.get("totalElements") or len(content)

    items = []
    for item in content:
        items.append(
            DpProjectItem(
                gid=item.get("assetGlobalId") or "",
                aid=item.get("assetId") or "",
                eid=item.get("elementId") or "",
                display_name=item.get("displayName") or item.get("description"),
                description=item.get("description"),
                asset_type=item.get("type"),
            )
        )

    return DpProjectListResponse(items=items, total=total, page=page, size=size)


@router.get("/projects/workplans", response_model=DpWorkplanListResponse)
async def list_dp_workplans(
    gid: str = Query(..., description="DP assetGlobalId (URL)"),
    aid: str = Query(..., description="DP assetId (full URI)"),
    eid: str = Query(..., description="DP elementId"),
):
    """
    특정 DP 프로젝트의 VM 실행 가능 워크플랜 목록을 반환합니다.
    패턴 A/B/C를 자동 판별하여 실행 단위 workplan 목록을 응답합니다.
    """
    try:
        xml = await dp_client.get_element_xml(aid=aid, eid=eid)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DP element 조회 실패: {e}")

    if not xml:
        raise HTTPException(status_code=404, detail="xmlStr이 비어 있습니다.")

    try:
        wp_list = extract_vm_workplans(xml)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"워크플랜 파싱 실패: {e}")

    return DpWorkplanListResponse(
        gid=gid,
        aid=aid,
        eid=eid,
        workplans=[DpWorkplanItem(**wp) for wp in wp_list],
    )


@router.get("/projects/thumbnail", summary="DP 원본 프로젝트 썸네일 이미지")
async def get_dp_project_thumbnail(
    gid: str = Query(..., description="DP assetGlobalId (URL)"),
    aid: str = Query(..., description="DP assetId (full URI)"),
    eid: str = Query(..., description="DP elementId"),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    """
    DP 원본 프로젝트 선택 단계에서 사용할 TITLE_IMAGE 썸네일 이미지를 반환합니다.
    """
    content, media_type = await svc.get_dp_project_thumbnail(
        gid=gid,
        aid=aid,
        eid=eid,
    )
    return Response(content=content, media_type=media_type)
