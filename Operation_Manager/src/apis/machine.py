from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/machines", tags=["Project Management"])

@router.get("/", status_code=201, response_model=ProjectListResponse, summary="프로젝트 리스트 호출")
async def upload_project(
    
):
    """
    프로젝트 XML 파일을 업로드하는 API입니다.

    - 업로드된 XML 파일을 파싱하여 프로젝트를 생성합니다.
    - 프로젝트는 데이터베이스에 저장됩니다.
    - **반환값**: 생성된 프로젝트의 정보
    """
    return