from fastapi import APIRouter, Depends
from src.schemas.project import ProjectSearchFilter, ProjectListResponse, NcCodeUpdateRequest, NCCodeResponse, WorkplanNCResponse
from src.services import ProjectService, get_project_service

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
    
@router.get("/projects/{project_id}/workplans/{workplan_id}/nc/{nc_id}", response_model=NCCodeResponse)
async def get_nc_code(
    project_id: str, 
    workplan_id: str, 
    nc_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    return await project_service.get_nc_code(project_id, workplan_id, nc_id)

@router.put("/projects/{project_id}/workplans/{workplan_id}/nc/{nc_id}")
async def update_nc_code(
    project_id: str, 
    workplan_id: str, 
    nc_id: str, 
    req: NcCodeUpdateRequest,
    project_service: ProjectService = Depends(get_project_service)
):
    return await project_service.update_nc_code(project_id, workplan_id, nc_id, req.content)