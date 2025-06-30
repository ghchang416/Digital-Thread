from fastapi import APIRouter, Depends
from src.schemas.project import ProductLogResponse, ProjectSearchFilter, ProjectListResponse, NcCodeUpdateRequest, NCCodeResponse, WorkplanNCResponse
from src.services import ProjectService, get_project_service

router = APIRouter(prefix="/api/projects", tags=["Project Management"])

@router.get("/", response_model=ProjectListResponse, summary="프로젝트 목록 조회")
async def get_project_list(
    filter: ProjectSearchFilter = Depends(),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    등록된 모든 프로젝트 리스트를 페이징/검색 조건에 맞게 반환합니다.

    - Query Params: name(부분 검색), project_id 등
    - Returns: 프로젝트 목록, 페이징 정보
    """
    result = await project_service.get_project_list(filter)

    return ProjectListResponse(
        projects=result["items"],
        page=filter.page,
        limit=filter.limit,
        total=result["total_count"]
    )

@router.get("/{project_id}/workplans", response_model=WorkplanNCResponse, summary="특정 프로젝트 내 모든 Workplan-NC 매핑 정보 조회")
async def extract_workplan_and_nc(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    """
    프로젝트 내 존재하는 모든 Workplan과 연결된 NC 코드 정보를 반환합니다.

    - Params:
        - project_id: 조회할 프로젝트 ID
    - Returns: Workplan별 NC 코드 ID/파일명 매핑
    """
    return await project_service.extract_workplan_and_nc(project_id)
    
@router.get("/{project_id}/workplans/{workplan_id}/nc/{nc_id}", response_model=NCCodeResponse, summary="워크플랜에 연결된 NC 코드 원본 내용 조회")
async def get_nc_code(
    project_id: str, 
    workplan_id: str, 
    nc_id: str,
    project_service: ProjectService = Depends(get_project_service)
):
    """
    특정 프로젝트-워크플랜-NC코드 조합에 대한 실제 NC 파일 내용을 반환합니다.

    - Params:
        - project_id: 프로젝트 ID
        - workplan_id: 워크플랜 ID
        - nc_id: NC 파일의 GridFS ID
    - Returns: NC 파일 텍스트 내용
    """
    return await project_service.get_nc_code(project_id, workplan_id, nc_id)

@router.put("/{project_id}/workplans/{workplan_id}/nc/{nc_id}", summary="NC 코드 업데이트 (파일 교체 및 XML 갱신)")
async def update_nc_code(
    project_id: str, 
    workplan_id: str, 
    nc_id: str, 
    req: NcCodeUpdateRequest,
    project_service: ProjectService = Depends(get_project_service)
):
    """
    워크플랜의 NC 코드를 새 내용으로 교체합니다. (파일/ID/프로젝트 XML 동시 갱신)

    - Params:
        - project_id: 프로젝트 ID
        - workplan_id: 워크플랜 ID
        - nc_id: NC 파일의 기존 ID
        - req: 새로운 NC 파일 내용 (body)
    - Returns: 성공 시 200, 실패 시 에러
    """
    return await project_service.update_nc_code(project_id, workplan_id, nc_id, req.content)

@router.get("/{project_id}/logs", response_model=ProductLogResponse, summary="프로젝트별 가공 이력(log) 전체 조회")
async def get_product_logs(
    project_id: str, 
    project_service: ProjectService = Depends(get_project_service)
):
    """
    해당 프로젝트의 전체 가공 이력(로그)을 반환합니다.

    - Params:
        - project_id: 프로젝트 ID
    - Returns: 가공 로그 리스트
    """
    return await project_service.get_product_logs_by_project_id(project_id)

@router.get("/{project_id}/nc/status", summary="프로젝트별 NC 파일 상태 현황(장비-파일-상태 매핑) 조회")
async def get_project_machine_status(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
):
    """
    프로젝트 내 NC 파일별 장비-상태 현황(등록/가공중/완료 등)을 조회합니다.

    - Params:
        - project_id: 프로젝트 ID
    - Returns: 각 NC 파일별 장비-상태 딕셔너리
    """
    return await project_service.get_machine_status_info(project_id)
