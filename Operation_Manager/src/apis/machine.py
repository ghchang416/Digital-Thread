from fastapi import APIRouter, Depends
from src.schemas.machine import MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse
from src.services import MachineService, get_machine_service

router = APIRouter(prefix="/api/machines", tags=["Machine Management"])

@router.get("/", response_model=MachineListResponse, summary="전체 장비 목록 조회")
async def get_machine_list(
    macine_service: MachineService = Depends(get_machine_service)
):
    """
    전체 CNC 장비 목록을 조회합니다.

    - Returns: 등록된 모든 CNC 장비의 상세 정보 목록 (id, ip, vendor 등)
    """
    return await macine_service.get_machine_list()

@router.post("/{machine_id}/send_nc", response_model=MachineFileUploadResponse, summary="NC 파일을 Torus로 업로드(전송)")
async def upload_torus_file(
    project_id: str, 
    machine_id: int, 
    nc_id: str, 
    service: MachineService = Depends(get_machine_service)
):
    """
    특정 프로젝트의 NC 파일을 선택한 CNC 장비에 업로드합니다.

    - Params:
        - project_id: NC 파일이 속한 프로젝트 ID
        - machine_id: NC 파일을 업로드할 장비의 ID
        - nc_id: 업로드할 NC 파일의 GridFS ID
    - Returns: 업로드된 파일 정보 및 상태
    """
    return await service.upload_torus_file(project_id, machine_id, nc_id)

@router.get("/{machine_id}/status", response_model=MachineProgramStatusResponse, summary="CNC 장비의 실시간 상태 조회")
async def get_machine_status(
    machine_id: int, 
    macine_service: MachineService = Depends(get_machine_service)
):
    """
    특정 CNC 장비의 가공 상태(programMode)를 조회합니다.

    - Params:
        - machine_id: 상태를 조회할 CNC 장비 ID
    - Returns: 장비의 가공 상태(대기/가공/완료 등)
    """
    return await macine_service.get_machine_status(machine_id)
