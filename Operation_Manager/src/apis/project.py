from fastapi import APIRouter, Depends
from src.schemas.project import ProjectSearchFilter, ProjectListResponse
from src.services import ProjectService, get_project_service

router = APIRouter(prefix="/api/projects", tags=["Project Management"])

@router.get("/projects", response_model=ProjectListResponse)
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