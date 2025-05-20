from fastapi import APIRouter, Depends, File, Path, Query
from fastapi.responses import FileResponse, StreamingResponse
from src.services import get_file_service, FileService, ProjectService, get_project_service
from src.utils.exceptions import CustomException, ExceptionEnum

router = APIRouter(prefix="/api/download", tags=["File Download"])

'''
============================================== 파일 다운로드 API ==============================================
'''

@router.get("/stp", status_code=200, summary="STEP 파일 다운로드")
async def download_step_file(
    project_id: str = Query(..., description="프로젝트의 ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    STEP(STP) 파일을 다운로드하는 API입니다.

    - 프로젝트 ID를 입력하여 저장된 STEP 파일을 다운로드할 수 있습니다.
    - **반환값**: STEP 파일 스트림
    """
    project: dict = await project_service.get_project_by_id(project_id)
    file_id = project.get("step_id")
    if not file_id:
        raise CustomException(ExceptionEnum.STP_NOT_FOUND)
    file_stream = await file_service.get_file_stream(file_id)
    return StreamingResponse(file_stream, media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={file_id}.STEP"})

@router.get("/stl", status_code=200, summary="STL 파일 다운로드")
async def download_stl_file(
    project_id: str = Query(..., description="프로젝트의 ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    STL 파일을 다운로드하는 API입니다.

    - 프로젝트에서 STL 파일을 조회하여 스트리밍 방식으로 반환합니다.
    - **반환값**: 다운로드 가능한 STL 파일 스트림
    """
    project: dict = await project_service.get_project_by_id(project_id)
    file_id = project.get("stl_id")
    if not file_id:
        raise CustomException(ExceptionEnum.STP_NOT_FOUND)
    file_stream = await file_service.get_file_stream(file_id)
    return StreamingResponse(
        file_stream, media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={file_id}.stl"}
    )

@router.get("/nc", status_code=200, summary="NC 파일 다운로드")
async def download_nc_file(
    nc_id: str = Query(..., description="다운로드할 NC 파일의 Id"),
    workplan_id: str = Query(..., description="NC 파일이 속한 workplan Id"),
    project_id: str = Query(..., description="프로젝트의 ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    NC(Numerical Control) 파일을 다운로드하는 API입니다.

    - 여러 개의 NC 파일이 있을 경우, **인덱스(index)를 사용하여 특정 파일을 다운로드**할 수 있습니다.
    - **반환값**: NC 파일 스트림
    """
    project: dict = await project_service.get_project_by_id(project_id)
    project_service.valid_file_id(project, workplan_id, nc_id, "nc_code")
    file_stream = await file_service.get_file_stream(nc_id)
    return StreamingResponse(file_stream, media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={nc_id}.nc"})

@router.get("/vm", status_code=200, summary="Virtual Machine (VM) 파일 다운로드")
async def download_vm_file(
    vm_id: str = Query(..., description="다운로드할 VM 파일의 Id"),
    workplan_id: str = Query(..., description="VM 파일이 속한 workplan Id"),
    project_id: str = Query(..., description="프로젝트의 ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    Virtual Machine (VM) 파일을 다운로드하는 API입니다.

    - 프로젝트에서 VM 파일 목록 중 특정 인덱스의 파일을 스트리밍 방식으로 반환합니다.
    - **반환값**: 다운로드 가능한 VM 파일 스트림
    """
    project: dict = await project_service.get_project_by_id(project_id)
    project_service.valid_file_id(project, workplan_id, vm_id, "vm")
    file_stream = await file_service.get_file_stream(vm_id)
    return StreamingResponse(file_stream, media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={vm_id}.val"}
    )

@router.get("/tdms", status_code=200, summary="TDMS 파일 다운로드")
async def download_tdms_file(
    tdms_log_id: str = Query(..., description="다운로드할 TDMS 로그 파일의 Id"),
    workplan_id: str = Query(..., description="TDMS 파일이 속한 workplan Id"),
    project_id: str = Query(..., description="프로젝트의 ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    TDMS 로그(Log) 파일을 다운로드하는 API입니다.
    
    - 프로젝트의 로그 파일을 다운로드할 수 있습니다.
    - 여러 개의 로그 파일이 있는 경우, **인덱스를 사용하여 특정 파일을 다운로드**할 수 있습니다.
    - **반환값**: 로그 파일 스트림
    """
    project: dict = await project_service.get_project_by_id(project_id)
    project_service.valid_file_id(project, workplan_id, tdms_log_id, "tdms")
    file_stream = await file_service.get_file_stream(tdms_log_id)
    return StreamingResponse(file_stream, media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={tdms_log_id}.tdms"}
    )
