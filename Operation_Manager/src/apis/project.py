from fastapi import APIRouter, BackgroundTasks, Depends
from src.schemas.project import ProductLogResponse, ProjectSearchFilter, ProjectListResponse, NcCodeUpdateRequest, NCCodeResponse, WorkplanNCResponse
from src.services import ProjectService, get_project_service, MachineService, get_file_service
from src.services.redis import RedisJobTracker

router = APIRouter(prefix="/api/projects", tags=["Project Management"])

@router.get("/", response_model=ProjectListResponse)
async def get_project_list(
    filter: ProjectSearchFilter = Depends(),
    project_service: ProjectService = Depends(get_project_service)
):
    result = await project_service.get_project_list(filter)

    return ProjectListResponse(
        projects=result["items"],
        page=filter.page,
        limit=filter.limit,
        total=result["total_count"]
    )

@router.get("/{project_id}/workplans", response_model=WorkplanNCResponse)
async def extract_workplan_and_nc(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    return await project_service.extract_workplan_and_nc(project_id)
    
@router.get("/{project_id}/workplans/{workplan_id}/nc/{nc_id}", response_model=NCCodeResponse)
async def get_nc_code(
    project_id: str, 
    workplan_id: str, 
    nc_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    return await project_service.get_nc_code(project_id, workplan_id, nc_id)

@router.put("/{project_id}/workplans/{workplan_id}/nc/{nc_id}")
async def update_nc_code(
    project_id: str, 
    workplan_id: str, 
    nc_id: str, 
    req: NcCodeUpdateRequest,
    project_service: ProjectService = Depends(get_project_service)
):
    return await project_service.update_nc_code(project_id, workplan_id, nc_id, req.content)

@router.get("/{project_id}/logs", response_model=ProductLogResponse)
async def get_product_logs(
    project_id: str, 
    project_service: ProjectService = Depends(get_project_service)
):
    return await project_service.get_product_logs_by_project_id(project_id)

@router.get("/{project_id}/initialize-job-cache")
async def initialize_job_cache(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
):
    result = await project_service.extract_workplan_and_nc(project_id)
    nc_filenames = [r.filename for r in result.results if r.filename]

    RedisJobTracker().initialize_project_cache(project_id, nc_filenames)

    return {"message": "Redis 캐시 초기화 "}


@router.get("/{project_id}/nc/status")
async def get_project_machine_status(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    return project_service.get_machine_status_info(project_id)

