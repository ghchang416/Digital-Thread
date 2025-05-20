from typing import Optional
from fastapi import APIRouter, Depends, File, Path, Body, UploadFile
from src.services import get_file_service, FileService, ProjectService, get_project_service
from src.schemas.file import FileCreateResponse, StpCreateResponse
from src.utils.exceptions import CustomException, ExceptionEnum

router = APIRouter(prefix="/api/upload", tags=["File Upload"])
"""
==============================================  파일 업로드 API ==============================================
"""

@router.post("/stp", status_code=201, response_model=StpCreateResponse, summary="STEP 파일 업로드")
async def upload_step_file(
    project_id: str = Body(..., description="프로젝트의 ID"),
    step_file: UploadFile = File(..., description="업로드할 STEP 파일"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    STEP(STP) 파일을 업로드하는 API입니다.

    - STEP 파일을 업로드하면 자동으로 STL 변환하여 함께 저장됩니다.
    - 변환된 STL 파일의 Id도 함께 프로젝트에 연결됩니다.
    - 반환값: 업로드된 STEP, STL 파일 ID
    """
    project = await project_service.get_project_by_id(project_id)
    stp_stl_flie: dict = await file_service.stp_upload(step_file)
    await project_service.stp_upload(project['_id'], stp_stl_flie)
    return StpCreateResponse(**stp_stl_flie)

@router.post("/nc", status_code=201, response_model=FileCreateResponse, summary="NC 파일 업로드")
async def upload_nc_file(
    project_id: str = Body(..., description="프로젝트의 ID"),
    workplan_id: str = Body(..., description="프로젝트의 WorkPlan"),
    nc_file: UploadFile = File(..., description="업로드할 NC 파일"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    NC (Numerical Control) 파일을 업로드하는 API입니다.

    - 업로드한 NC 파일의 Id가 프로젝트 데이터에 저장합니다.
    - NC 파일의 확장자 유형을 자동 감지하여 저장됩니다.
    - **반환값**: 업로드된 NC 파일의 ID
    """
    project = await project_service.get_project_by_id(project_id)
    file_ext, file_id = await file_service.process_upload(nc_file)
    await project_service.nc_upload(project, workplan_id, file_id)
    return FileCreateResponse(file_id=file_id)

@router.post("/vm", status_code=201, response_model=FileCreateResponse, summary="Virtual Machine 파일 업로드")
async def upload_virtual_machine_file(
    project_id: str = Body(..., description="프로젝트의 ID"),
    workplan_id: str = Body(..., description="프로젝트의 WorkPlan"),
    nc_code_id: str = Body(..., description="프로젝트의 NC Code"),
    vm_file: UploadFile = File(..., description="업로드할 Virtual Machine (VM) 파일"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    Virtual Machine (VM) 파일을 업로드하는 API입니다.

    - 업로드된 VM 파일의 Id가 프로젝트 데이터에 저장됩니다.
    - **반환값**: 업로드된 VM 파일의 ID
    """
    project = await project_service.get_project_by_id(project_id)
    await file_service.file_exist(nc_code_id)
    file_ext, file_id = await file_service.process_upload(
        vm_file, {"nc_code": nc_code_id}
    )
    await project_service.vm_upload(project, workplan_id, file_id)
    return FileCreateResponse(file_id=file_id)
     
@router.post("/tdms", status_code=201, response_model=FileCreateResponse, summary="TDMS 확장 로그 파일 업로드")
async def upload_tdms_path_log(
    project_id: str = Body(..., description="프로젝트의 ID"),
    workplan_id: str = Body(..., description="프로젝트의 WorkPlan"),
    nc_code_id: str = Body(..., description="프로젝트의 NC Code"),
    tdms_path: Optional[str] = Body(None, description="업로드할 TDMS 파일 경로"),
    log_file: Optional[UploadFile] = File(None, description="업로드할 TDMS 확장 로그 파일"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    TDMS 파일의 경로와 (Log) 파일을 업로드하는 API입니다.

    - 프로젝트와 연결된 로그 파일의 Id를 업로드하여 기록합니다.
    - **반환값**: 업로드된 로그 파일의 ID
    """
    project = await project_service.get_project_by_id(project_id)
    await file_service.file_exist(nc_code_id)
    file_ext, file_id = await file_service.process_upload(
        log_file, {"nc_code": nc_code_id}
    )
    await project_service.tdms_upload(project, workplan_id, file_id, tdms_path)
    return FileCreateResponse(file_id=file_id)

@router.post("/cam", status_code=201, summary="CAM 파일 업로드")
async def upload_cam_file(
    project_id: str = Body(..., description="프로젝트의 ID"),
    cam_type: str = Body(..., description="CAM 타입 (NX 또는 PowerMill)"),
    cam_json: UploadFile = File(..., description="CAM JSON 파일"),
    mapping_json: UploadFile = File(..., description="CAM 매핑 JSON 파일"),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    CAM (Computer-Aided Manufacturing) 파일을 업로드하는 API입니다.

    - NX 또는 PowerMill CAM JSON 데이터를 업로드합니다.
    - CAM 데이터를 프로젝트에 반영한 후 XML 형식으로 변환하여 저장합니다.
    - **반환값**: 업로드된 CAM JSON 파일의 ID
    """
    project = await project_service.get_project_by_id(project_id)
    await project_service.add_cam_to_proejct(project, cam_type, cam_json, mapping_json)
    return

