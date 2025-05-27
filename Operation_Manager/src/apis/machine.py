from fastapi import APIRouter, Depends
from src.schemas.machine import MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse
from src.services import MachineService, get_file_service

router = APIRouter(prefix="/api/machines", tags=["Machine Management"])

@router.get("/", response_model=MachineListResponse)
async def get_machines(
    macine_service: MachineService = Depends()
):
    return await macine_service.get_machine_list()

@router.post("/{machine_id}/send_nc", response_model=MachineFileUploadResponse)
async def upload_file_to_machine(
    machine_id: int, 
    file_id: str, 
    service: MachineService = Depends()
):
    return await service.upload_torus_file(machine_id, file_id)

@router.get("/machine/{machine_id}/status", response_model=MachineProgramStatusResponse)
async def get_machine_status(
    machine_id: int, 
    macine_service: MachineService = Depends()
):
    return await macine_service.get_machine_status(machine_id)