from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from bson import ObjectId
from src.schemas.vm_project import (
    VmProjectCreateIn,
    StartVmIn,
    CreateFromIsoOut,
    ProjectFileOut,
    ProcessAnnotationsResponse,
    StockPatchIn,
    ProcessPatchIn,
    PreviewFromIsoOut,
    VmProjectListResponse,
    VmProjectStatusEnum,
    VmProjectDetailOut,
    StockItemsResponse,
)
from src.services.vm_project import VmProjectService
from src.database import get_vm_project_service

router = APIRouter(prefix="/vm-project", tags=["vm-project"])


@router.post("")
async def create_full(
    payload: VmProjectCreateIn, svc: VmProjectService = Depends(get_vm_project_service)
):
    """
    VM 프로젝트를 생성합니다.
    - source : 데이터 소스 ("iso" 또는 "dp", 기본값 "iso")
    - gid : 프로젝트의 global_asset_id
    - aid : 프로젝트의 asset_id
    - eid : 프로젝트의 element_id
    - wpid : 워크플랜 its_id
    """
    if payload.source == "dp":
        result = await svc.create_full_from_dp(payload)
    else:
        result = await svc.create_full_from_iso(payload)
    return result


@router.get("", response_model=VmProjectListResponse, summary="VM 프로젝트 목록")
async def list_vm_projects(
    status: VmProjectStatusEnum | None = Query(None, description="필터: 상태"),
    gid: str | None = Query(None, description="필터: 글로벌 자산 ID"),
    aid: str | None = Query(None, description="필터: 자산 ID"),
    q: str | None = Query(None, description="검색어(proj_name/eid)"),
    page: int = Query(1, ge=1, description="페이지(1-base)"),
    size: int = Query(20, ge=1, le=100, description="페이지 크기"),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    return await svc.list_projects(
        status=status.value if status else None,
        gid=gid,
        aid=aid,
        q=q,
        page=page,
        size=size,
    )


@router.get(
    "/stocks", response_model=StockItemsResponse, summary="Stock 타입 목록(정적)"
)
async def list_stocks(
    q: str | None = Query(None, description="검색어: code(정확) 또는 name(부분 일치)"),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    return await svc.list_stock_items(q=q)


@router.get(
    "/{vm_project_id}", response_model=VmProjectDetailOut, summary="VM 프로젝트 상세"
)
async def get_vm_project_detail(
    vm_project_id: str,
    svc: VmProjectService = Depends(get_vm_project_service),
):
    return await svc.get_detail(ObjectId(vm_project_id))


@router.get("/{vm_project_id}/thumbnail", summary="VM 프로젝트 썸네일 이미지")
async def get_vm_project_thumbnail(
    vm_project_id: str,
    svc: VmProjectService = Depends(get_vm_project_service),
):
    """
    VM 프로젝트 썸네일 이미지를 반환합니다.

    - DP source: 같은 gid 아래 `TITLE_IMAGE` dt_file을 찾아 path 기반으로 파일 다운로드
    - ISO source 또는 이미지 없음: 404
    """
    content, media_type = await svc.get_thumbnail(ObjectId(vm_project_id))
    return Response(content=content, media_type=media_type)


@router.post("/{vm_project_id}/poll")
async def poll_vm(
    vm_project_id: str,
    svc: VmProjectService = Depends(get_vm_project_service),
):
    """
    특정 VM 프로젝트의 상태를 즉시 폴링합니다.
    running 상태인 프로젝트만 폴링하며, VM 상태에 따라 completed / failed 로 전환합니다.
    """
    try:
        token = await svc._vm_issue_token()
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"VM 토큰 발급 실패: {e}")
    return await svc.poll_vm_status(ObjectId(vm_project_id), token=token)


@router.post("/{vm_project_id}/reset", summary="VM 프로젝트 리셋 (failed → ready)")
async def reset_vm_project(
    vm_project_id: str,
    svc: VmProjectService = Depends(get_vm_project_service),
):
    """
    'failed' 상태의 VM 프로젝트를 'ready'로 리셋합니다.
    vm_job_id, vm_error_message, vm_raw_status를 초기화하여 재실행을 허용합니다.
    """
    return await svc.reset_to_ready(ObjectId(vm_project_id))


@router.post("/{vm_project_id}/start-vm")
async def start_vm(
    vm_project_id: str,
    body: StartVmIn = StartVmIn(),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    """
    VM 가상가공을 시작합니다.

    - **upload_result**: VM 완료 후 결과 처리 방식
      - `true` (기본값): 결과 ZIP을 직접 다운로드하여 데이터 플랫폼에 파일로 업로드
      - `false`: 결과 파일 링크(URL)만 dt_file의 path 필드에 저장
    """
    return await svc.start_vm_job(ObjectId(vm_project_id), upload_result=body.upload_result)


# @router.post("/from-iso/preview", response_model=PreviewFromIsoOut)
# async def preview_from_iso(
#     body: VmProjectCreateIn,
#     svc: VmProjectService = Depends(get_vm_project_service),
# ):
#     """
#     DB에 저장하지 않고 stock/project_file만 리턴하는 미리보기.
#     - stock: material 기반 자동 계산
#     - process: (지정 workplan 또는 main) 워킹스텝 순서대로,
#                NC 분할 기반 file_path/output_dir_path + tool_data 채움
#     """
#     try:
#         stock, project_file, _debug = await svc.preview_from_iso_with_nc(body)
#         return PreviewFromIsoOut(stock=stock, project_file=project_file)

#     except HTTPException:
#         # svc 내부에서 404(워크플랜 없음) 등을 일으킨 경우 그대로 전달
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=502, detail=f"ISO 조회/stock 계산 실패: {e}")


@router.get("/{vm_project_id}/project-file", response_model=ProjectFileOut)
async def get_project_file(
    vm_project_id: str = Path(..., description="vm_project _id"),
    is_file: str = Query("false", description="파일 기반 조회 여부 (true/false)"),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    try:
        if is_file.lower() == "true":
            return await svc.get_project_file(ObjectId(vm_project_id), source="file")
        else:
            return await svc.get_project_file(ObjectId(vm_project_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"프로젝트 파일 조회 실패: {e}")


@router.get(
    "/{vm_project_id}/process-annotations",
    response_model=ProcessAnnotationsResponse,
    summary="프로세스 보조 메타데이터 조회",
)
async def get_process_annotations(
    vm_project_id: str = Path(..., description="vm_project _id"),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    try:
        return await svc.get_process_annotations(ObjectId(vm_project_id))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"process annotations 조회 실패: {e}")


@router.patch("/{vm_project_id}/project-file/stock", response_model=ProjectFileOut)
async def patch_stock(
    body: StockPatchIn,
    vm_project_id: str = Path(...),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    try:
        return await svc.patch_stock(ObjectId(vm_project_id), body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"stock 수정 실패: {e}")


@router.patch("/{vm_project_id}/project-file/process", response_model=ProjectFileOut)
async def patch_process(
    body: ProcessPatchIn,
    vm_project_id: str = Path(...),
    svc: VmProjectService = Depends(get_vm_project_service),
):
    try:
        return await svc.patch_process(ObjectId(vm_project_id), body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"process 수정 실패: {e}")


# @router.post("/debug/material")
# async def debug_material(
#     body: VmProjectCreateIn, svc: VmProjectService = Depends(get_vm_project_service)
# ):
#     try:
#         return await svc.debug_iso_material(body)
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"debug failed: {e}")
