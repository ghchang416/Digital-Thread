import logging
import json
from fastapi import (
    APIRouter,
    Depends,
    File,
    Path,
    Query,
    Response,
    UploadFile,
    HTTPException,
    status,
)
from fastapi.responses import PlainTextResponse, StreamingResponse
from src.services import (
    FileService,
    AssetService,
    get_file_service,
    get_asset_service,
)
from src.schemas.asset import (
    AssetCreateResponse,
    AssetListResponse,
    GlobalAssetListResponse,
    AssetIdListResponse,
    GroupedAssetIdsResponse,
)
from src.utils.exceptions import CustomException, ExceptionEnum
import requests
from src.config import settings

from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/api/v3/assets", tags=["Asset Management(v3)"])


@router.post(
    "",
    summary="Asset 업로드(분할/부분성공, is_upload=False)",
)
async def upload_asset(
    xml: UploadFile = File(
        ..., description="업로드할 dt_asset XML (여러 dt_elements 포함 가능)"
    ),
    upload_files: Optional[List[UploadFile]] = File(
        None, description="dt_file 요소들과 매칭되는 실제 파일들(여러 개 가능)"
    ),
    asset_service: AssetService = Depends(get_asset_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    동작:
    - XML 내 여러 dt_elements를 분할 저장
    - dt_file 요소는 display_name과 동일한 업로드 파일이 필수
    - NC 파일은 (DT_PROJECT, WORKPLAN) 1:1 참조 중복 금지
    - 저장된 문서는 is_upload=False 로 기본 저장 (외부 업로드 전 상태)
    - 서비스는 예외를 던지지 않고 요소별 성공/실패를 results/summary 로 반환
    - API는 summary를 보고 상태코드 결정:
        * 모두 성공: 201 Created
        * 일부 성공: 206 Partial Content
        * 모두 실패: 400 Bad Request
    """
    # 1) XML 바디 읽기
    try:
        xml_string = (await xml.read()).decode("utf-8", errors="ignore")
    except Exception as e:
        # 파일 자체를 못 읽으면 요청 전체 실패
        payload = {
            "results": [
                {
                    "element_id": None,
                    "status": "failed",
                    "reason": f"xml-read-failed: {e}",
                }
            ],
            "summary": {"total": 1, "created": 0, "failed": 1},
        }
        return Response(
            content=json.dumps(payload, ensure_ascii=False),
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    # 2) 서비스 호출 (예외 대신 결과 dict 반환)
    try:
        result = await asset_service.create_from_xml_multi(
            xml=xml_string,
            upload_files=upload_files,
            file_service=file_service,
            validate_schema=True,  # 스키마 실패도 요소 실패로 집계
        )
    except Exception as e:
        # 예상치 못한 시스템 에러(서비스 설계상 드뭄)
        logging.exception("Unexpected error in create_from_xml_multi: %s", e)
        payload = {
            "results": [
                {
                    "element_id": None,
                    "status": "failed",
                    "reason": f"unexpected-error: {e}",
                }
            ],
            "summary": {"total": 1, "created": 0, "failed": 1},
        }
        return Response(
            content=json.dumps(payload, ensure_ascii=False),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json",
        )

    # 3) 상태 코드 결정 (201/206/400)
    summary = result.get("summary") or {}
    total = int(summary.get("total") or 0)
    created = int(summary.get("created") or 0)

    if total == 0:
        # 업로드할 요소가 없는 경우: 클라이언트 입력 문제로 간주
        return Response(
            content=json.dumps(result, ensure_ascii=False),
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    if created == 0:
        # 모두 실패
        return Response(
            content=json.dumps(result, ensure_ascii=False),
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    if created < total:
        # 부분 성공
        return Response(
            content=json.dumps(result, ensure_ascii=False),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            media_type="application/json",
        )

    # 모두 성공
    return Response(
        content=json.dumps(result, ensure_ascii=False),
        status_code=status.HTTP_201_CREATED,
        media_type="application/json",
    )


@router.get("", response_model=AssetListResponse, summary="Asset 목록 조회")
async def get_asset_list(
    global_asset_id: str = Query(..., description="조회할 asset의 글로벌 에셋 Id"),
    asset_id: str = Query(None, description="조회할 asset의 에셋 Id"),
    type: str = Query(None, description="조회할 asset의 에셋 type"),
    asset_service: AssetService = Depends(get_asset_service),
):
    """
    asset 목록을 조회하는 API입니다.

    - 저장된 asset의 document를 반환합니다.
    - **반환값**: asset document 리스트
    """
    return await asset_service.list_assets(
        global_asset_id=global_asset_id,
        asset_id=asset_id,
        type=type,
    )


@router.put("", summary="Asset 수정(XML 교체, 선택 파일 교체)")
async def update_asset(
    asset_mongo_id: str = Query(..., description="업데이트할 asset의 mongo_id"),
    xml: UploadFile = File(..., description="교체할 dt_asset XML"),
    upload_file: UploadFile | None = File(None, description="dt_file 바이너리(옵션)"),
    asset_service: AssetService = Depends(get_asset_service),
    file_service: FileService = Depends(get_file_service),
):
    xml_string = (await xml.read()).decode("utf-8", errors="ignore")

    # 파일 없이 XML만 교체
    if upload_file is None:
        try:
            await asset_service.update_from_xml(
                mongo_id=asset_mongo_id,
                xml=xml_string,
                forbid_type_change=True,  # type 변경 금지
                precheck_dup_conflict=True,  # 키 변경시 중복 선검사
            )
            return {"ok": True}
        except CustomException as ce:
            if ce.enum == ExceptionEnum.NO_DATA_FOUND:
                raise HTTPException(status_code=404, detail="Asset not found")
            if ce.enum == ExceptionEnum.ASSET_ID_DUPLICATION:
                raise HTTPException(status_code=409, detail="Duplicate asset keys")
            raise HTTPException(status_code=400, detail=str(ce))

    # 파일 교체 플로우: 새 파일 업로드 → XML 패치+업데이트 → 성공 시 기존 파일 삭제 / 실패 시 새 파일 롤백
    new_file_id = await file_service.process_upload(file=upload_file)
    try:
        old_file_id = await asset_service.update_from_xml_with_file_id(
            mongo_id=asset_mongo_id,
            xml=xml_string,
            new_file_id=new_file_id,
            fill="value",  # 필요시 "path"/"both"
            overwrite=True,
            path_template="gridfs://{oid}",
            forbid_type_change=True,
            precheck_dup_conflict=True,
        )
    except CustomException as ce:
        # 업데이트 실패 → 새 파일 롤백
        try:
            await file_service.delete(new_file_id)
        finally:
            pass
        if ce.enum == ExceptionEnum.NO_DATA_FOUND:
            raise HTTPException(status_code=404, detail="Asset not found")
        if ce.enum == ExceptionEnum.ASSET_ID_DUPLICATION:
            raise HTTPException(status_code=409, detail="Duplicate asset keys")
        raise HTTPException(status_code=400, detail=str(ce))

    # 성공 후, 구 파일 정리(있으면 베스트에포트)
    if old_file_id:
        try:
            await file_service.delete_file_by_id(old_file_id)
        except Exception:
            # 로그만 남기고 무시
            pass

    return {"ok": True}


@router.delete("", summary="에셋 삭제(using keys) - dt_file이면 파일도 삭제")
async def delete_asset_by_keys(
    global_asset_id: str = Query(...),
    asset_id: str = Query(...),
    type: str = Query(...),
    element_id: str = Query(...),
    asset_service: AssetService = Depends(get_asset_service),
    file_service: FileService = Depends(get_file_service),
):
    try:
        result = await asset_service.delete_asset(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            type=type,
            element_id=element_id,
            file_service=file_service,
            delete_file=True,
        )
        return result
    except CustomException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/extract", response_class=PlainTextResponse, summary="자산 병합 뷰")
async def extract_assets(
    global_asset_id: str = Query(..., description="필수: 글로벌 자산 ID"),
    asset_id: str = Query(..., description="선택: 특정 asset_id만"),
    type: str | None = Query(
        None, description="선택: 동일 타입만(nc/tdms/vm/tool/machine 등 별칭 허용)"
    ),
    element_id: str | None = Query(
        None, description="선택: element_id 지정 시 단일 원문 반환"
    ),
    asset_service: AssetService = Depends(get_asset_service),
):
    """
    동작 규칙
    - element_id 있으면: 조건과 일치하는 단건 원문 XML 그대로 반환
    - element_id 없으면: 조건에 맞는 모든 문서의 dt_elements를 합쳐서 하나의 dt_asset으로 반환
    - type이 주어지면: 동일 타입만 모아서 합침(별칭 nc/tdms/vm/tool/machine 지원)
    """
    try:
        xml = await asset_service.extract(
            global_asset_id=global_asset_id,
            asset_id=asset_id,
            type=type,
            element_id=element_id,
        )
        return PlainTextResponse(xml, media_type="application/xml")
    except CustomException as e:
        # 통일된 에러 응답
        return PlainTextResponse(e.detail, status_code=e.status_code)


@router.get("/file-download")
async def download_file_by_asset_keys(
    global_asset_id: str = Query(...),
    asset_id: str = Query(...),
    element_id: str = Query(...),
    asset_service: AssetService = Depends(get_asset_service),
    file_service: FileService = Depends(get_file_service),
):
    """
    특정 에셋 키(global_asset_id, asset_id, element_id)에 해당하는 dt_file을 찾아
    MongoDB GridFS에 저장된 실제 파일을 다운로드하는 엔드포인트.

    Workflow:
    1. AssetService를 통해 XML에서 <value>에 저장된 파일 ObjectId(OID)와 메타데이터(display_name, content_type)를 조회
    2. FileService를 통해 해당 OID로 GridFS에서 파일 스트림(grid_out)을 획득
    3. grid_out.readchunk()를 이용해 파일을 chunk 단위로 비동기 스트리밍
    4. StreamingResponse로 클라이언트에 전송
       - Content-Type: XML의 content_type 값 또는 기본값(application/octet-stream)
       - Content-Disposition: 파일명(display_name 또는 filename, 없으면 OID)

    Args:
        global_asset_id (str): 상위 자산 그룹(global asset)의 식별자
        asset_id (str): 특정 asset의 식별자
        element_id (str): dt_file element_id (다운로드할 파일 XML 요소의 키)
        asset_service (AssetService): 의존성 주입된 AssetService, 파일 OID 및 메타 추출
        file_service (FileService): 의존성 주입된 FileService, GridFS 파일 스트림 조회

    Returns:
        StreamingResponse: GridFS 파일을 클라이언트로 스트리밍 다운로드

    Raises:
        HTTPException:
            - 404/CustomException: 에셋 또는 파일 OID가 없을 때
            - 기타 예외: 내부 오류 시 FastAPI가 기본 처리
    """
    try:
        oid, display_name, content_type = (
            await asset_service.get_file_oid_by_asset_keys(
                global_asset_id=global_asset_id,
                asset_id=asset_id,
                element_id=element_id,
            )
        )
        grid_out = await file_service.get_file_stream(oid)

        async def _iter_chunks():
            while True:
                chunk = await grid_out.readchunk()
                if not chunk:
                    break
                yield chunk

        fname = display_name or getattr(grid_out, "filename", None) or oid
        ctype = (
            content_type
            or getattr(grid_out, "content_type", None)
            or "application/octet-stream"
        )

        return StreamingResponse(
            _iter_chunks(),
            media_type=ctype,
            headers={"Content-Disposition": f'attachment; filename="{fname}"'},
        )
    except CustomException as ce:
        raise HTTPException(status_code=ce.status_code, detail=ce.detail)


@router.get(
    "/global-assets",
    response_model=GlobalAssetListResponse,
    summary="global_asset_id 목록 조회",
)
async def list_global_assets(
    asset_service: AssetService = Depends(get_asset_service),
):
    return await asset_service.list_global_asset_ids()


@router.get(
    "/global-assets/{global_asset_id}/asset-ids",
    response_model=AssetIdListResponse,
    summary="특정 글로벌의 asset_id 목록",
)
async def list_asset_ids_by_global(
    global_asset_id: str = Path(..., min_length=1, description="대상 global_asset_id"),
    asset_service: AssetService = Depends(get_asset_service),
):
    return await asset_service.list_asset_ids_by_global(global_asset_id)


@router.get(
    "/global-assets/asset-ids",
    response_model=GroupedAssetIdsResponse,
    summary="글로벌별 asset_id 목록(그룹핑)",
)
async def list_grouped_asset_ids(
    asset_service: AssetService = Depends(get_asset_service),
):
    return await asset_service.list_grouped_asset_ids()
