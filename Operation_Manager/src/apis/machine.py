from fastapi import APIRouter, BackgroundTasks, Depends
from src.schemas.machine import MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse
from src.services import MachineService, get_file_service

router = APIRouter(prefix="/api/machines", tags=["Machine Management"])

@router.get("/", response_model=MachineListResponse)
async def get_machine_list(
    macine_service: MachineService = Depends(get_file_service)
):
    return await macine_service.get_machine_list()

@router.post("/{machine_id}/send_nc", response_model=MachineFileUploadResponse)
async def upload_torus_file(
    project_id: str, 
    machine_id: int, 
    nc_id: str, 
    background_tasks: BackgroundTasks,
    service: MachineService = Depends(get_file_service)
):
    return await service.upload_torus_file(project_id, machine_id, nc_id, background_tasks)

@router.get("/{machine_id}/status", response_model=MachineProgramStatusResponse)
async def get_machine_status(
    machine_id: int, 
    macine_service: MachineService = Depends(get_file_service)
):
    return await macine_service.get_machine_status(machine_id)

@router.get("/{project_id}/job-status")
async def get_job_status(
    project_id: str, 
    macine_service: MachineService = Depends(get_file_service)
):
    machine_list_response = await macine_service.get_machine_list()
    machine_ids = [m.id for m in machine_list_response.machines]

    await macine_service.update_all_machine_job_status(project_id, machine_ids)
    return macine_service.get_machine_status_info(project_id)
