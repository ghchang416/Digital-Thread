import logging
from fastapi import (
    APIRouter,
    Depends,
    File,
    Path,
    Query,
    Response,
    UploadFile,
)
from src.services import (
    FileService,
    ProjectService,
    get_file_service,
    get_project_service,
)
from src.schemas.project import (
    ProjectCreateResponse,
    ProjectListResponse,
    ProjectResponse,
    TdmsPahtListResponse,
)
from src.utils.exceptions import CustomException, ExceptionEnum
import requests
from src.config import settings

router = APIRouter(prefix="/api/projects", tags=["Project Management"])


@router.post(
    "/",
    status_code=201,
    response_model=ProjectCreateResponse,
    summary="프로젝트 업로드",
)
async def upload_project(
    project_xml_file: UploadFile = File(..., description="업로드할 프로젝트 XML 파일"),
    project_service: ProjectService = Depends(get_project_service),
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
    project_service: ProjectService = Depends(get_project_service),
):
    """
    프로젝트 목록을 조회하는 API입니다.

    - 저장된 프로젝트의 ID 리스트를 반환합니다.
    - 프로젝트의 상세 정보가 필요하면 개별 조회 API를 사용하세요.
    - **반환값**: 프로젝트 ID 리스트
    """
    return await project_service.get_project_list()


@router.get(
    "/{project_id}", response_model=ProjectResponse, summary="프로젝트 상세 조회"
)
async def get_project_detail(
    project_id: str = Path(..., description="조회할 프로젝트 ID"),
    project_service: ProjectService = Depends(get_project_service),
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
    await project_service.delete_project_by_id(project["_id"])
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
    project_data = project_service.xml_to_dict(project["data"])
    extracted_data = project_service.get_inner_data(project_data, attribute_path)
    return Response(content=extracted_data, media_type="application/xml")


@router.get(
    "/{workplan_id}/tdms_list/",
    response_model=TdmsPahtListResponse,
    summary="TDMS list 추출",
)
async def extract_tdms_list_attribute(
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


@router.post("/{project_id}/generate-vm-project")
async def generate_vm_project(
    project_id: str,
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    # 프로젝트 정보 가져오기
    project = await project_service.repository.get_project_by_id(project_id)
    # VM용 프로젝트 데이터 만들기
    project_s3_path, nc_s3_path, project_id = await project_service.process_project_vm(
        project, file_service
    )

    # 토큰 발급
    vm_token_url = f"{settings.vm_api_url}/api/v1/auths/login/access-token"
    token_body = {
        "username": settings.vm_username,
        "password": settings.vm_password,
    }

    token_headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        token_res = requests.post(vm_token_url, data=token_body, headers=token_headers)
        token_res.raise_for_status()
        access_token = token_res.json()["access_token"]
    except requests.RequestException as e:
        logging.warning(msg=str(e))
        raise CustomException(ExceptionEnum.VM_AUTH_FAIL)
    except KeyError:
        raise CustomException(ExceptionEnum.VM_NOT_TOKEN)

    # 프로젝트 header, body 생성
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    body = {
        "machine_name": project_id,
        "upload_file_link1": project_s3_path,
        "upload_file_link2": nc_s3_path,
    }

    # vm프로젝트 생성 api 호출
    vm_url = f"{settings.vm_api_url}/api/v1/macsim"

    try:
        response = requests.post(vm_url, json=body, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise CustomException(ExceptionEnum.VM_PRJ_FAIL)
