from fastapi import APIRouter, Depends
from src.schemas.machine import MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse
from src.services import MachineService, get_machine_service

router = APIRouter(prefix="/api/machines", tags=["Machine Management"])

@router.get("/", response_model=MachineListResponse)
async def get_machine_list(
    macine_service: MachineService = Depends(get_machine_service)
):
    return await macine_service.get_machine_list()

@router.post("/{machine_id}/send_nc", response_model=MachineFileUploadResponse)
async def upload_torus_file(
    project_id: str, 
    machine_id: int, 
    nc_id: str, 
    service: MachineService = Depends(get_machine_service)
):
    return await service.upload_torus_file(project_id, machine_id, nc_id)

@router.get("/{machine_id}/status", response_model=MachineProgramStatusResponse)
async def get_machine_status(
    machine_id: int, 
    macine_service: MachineService = Depends(get_machine_service)
):
    return await macine_service.get_machine_status(machine_id)
