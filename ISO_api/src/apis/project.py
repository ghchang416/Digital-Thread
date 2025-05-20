import logging
from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile
from src.services import FileService, ProjectService, get_file_service, get_project_service
from src.schemas.project import ProjectCreateResponse, ProjectListResponse, ProjectResponse, TdmsPahtListResponse

router = APIRouter(prefix="/api/projects", tags=["Project Management"])

@router.post("/", status_code=201, response_model=ProjectCreateResponse, summary="프로젝트 업로드")
async def upload_project(
    project_xml_file: UploadFile = File(..., description="업로드할 프로젝트 XML 파일"),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    프로젝트 XML 파일을 업로드하는 API입니다.

    - 업로드된 XML 파일을 파싱하여 프로젝트를 생성합니다.
    - 프로젝트는 데이터베이스에 저장됩니다.
    - **반환값**: 생성된 프로젝트의 정보
    """
    xml_content = await project_xml_file.read()
    xml_string = xml_content.decode("utf-8")
    return await project_service.create_project(xml_string)

@router.get("/", response_model=ProjectListResponse, summary="프로젝트 목록 조회")
async def get_project_list(
    project_service: ProjectService = Depends(get_project_service)
):
    """
    프로젝트 목록을 조회하는 API입니다.

    - 저장된 프로젝트의 ID 리스트를 반환합니다.
    - 프로젝트의 상세 정보가 필요하면 개별 조회 API를 사용하세요.
    - **반환값**: 프로젝트 ID 리스트
    """
    return await project_service.get_project_list()

@router.get("/{project_id}", response_model=ProjectResponse, summary="프로젝트 상세 조회")
async def get_project_detail(
    project_id: str = Path(..., description="조회할 프로젝트 ID"),
    project_service: ProjectService = Depends(get_project_service)
):
    """
    특정 프로젝트의 상세 정보를 조회하는 API입니다.

    - 프로젝트 ID를 입력하면 해당 프로젝트의 데이터를 반환합니다.
    - **반환값**: 프로젝트의 상세 정보
    """
    return await project_service.get_project_by_id(project_id)

@router.delete("/{project_id}", status_code=204, summary="프로젝트 삭제")
async def delete_project(
    project_id: str = Path(..., description="삭제할 프로젝트 ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    특정 프로젝트를 삭제하는 API입니다.

    - 프로젝트와 관련된 모든 파일을 삭제한 후 프로젝트 자체를 삭제합니다.
    - **반환값**: 없음 (204 No Content)
    """
    project: dict = await project_service.get_project_by_id(project_id)
    await file_service.delete_project_files(project)
    await project_service.delete_project_by_id(project['_id'])
    return

@router.get("/extract/{attribute_path:path}", summary="XML 속성 추출")
async def extract_xml_attribute(
    attribute_path: str = Path(..., description="추출할 XML 속성의 경로"),
    project_id: str = Query(..., description="대상 프로젝트 ID"),
    project_service: ProjectService = Depends(get_project_service),
):
    """
    프로젝트의 XML 데이터에서 특정 속성을 추출하는 API입니다.

    - XML 내부에서 특정 경로(`attribute_path`)를 지정하여 값을 가져올 수 있습니다.
    - **반환값**: 해당 속성의 XML 데이터
    """
    project = await project_service.get_project_by_id(project_id)
    project_data = project_service.xml_to_dict(project['data'])
    extracted_data = project_service.get_inner_data(project_data, attribute_path)
    return Response(content=extracted_data, media_type="application/xml")

@router.get("/{workplan_id}/tdms_list/", response_model=TdmsPahtListResponse, summary="TDMS list 추출")
async def extract_xml_attribute(
    workplan_id: str = Path(..., description="추출할 TDMS의 Workplan Id"),
    project_id: str = Query(..., description="대상 프로젝트 ID"),
    project_service: ProjectService = Depends(get_project_service),
):
    """
    프로젝트의 XML 데이터에서 특정 속성을 추출하는 API입니다.

    - XML 내부에서 특정 workplan에 속하는 TDMS file들의 path를 가져올 수 있습니다.
    - **반환값**: TDMS path의 list 형식
    """
    project = await project_service.get_project_by_id(project_id)
    tdms_list = project_service.get_tdms_list(project, workplan_id)
    return TdmsPahtListResponse(tdms_list=tdms_list)
