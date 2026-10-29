import json

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from src.schemas.creator import PartialReviewRequest
from src.services.creator.catalog import get_catalog
from src.services.creator.preview import preview_assets
from src.schemas.creator_cam import CamParseRequest
from src.services.creator.cam import CamInputError, MAX_FILE_BYTES, parse_cam
from src.schemas.creator_nc import NcAnalyzeRequest, NcToolsRequest
from src.services.creator.nc import analyze_nc, compile_tools
from src.schemas.creator_completion import CompletionRequest
from src.services.creator.completion import complete_workplan
from src.schemas.creator_manual import ManualToolRequest, ManualStepRequest, ManualNcRequest
from src.services.creator.manual import manual_profile, prepare_tool, prepare_step, confirm_nc

router = APIRouter(prefix="/api/v3/creator", tags=["Project Creator"])


@router.get("/manual/profile")
def tool_profile():
    return manual_profile()


@router.post("/tools/prepare")
def manual_tool(request: ManualToolRequest):
    try:
        return prepare_tool(request)
    except (CamInputError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, CamInputError) else "공구 입력 형식을 확인해 주세요.") from exc


@router.post("/workplans/manual-step")
def manual_step(request: ManualStepRequest):
    try:
        return prepare_step(request)
    except (CamInputError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, CamInputError) else "워킹스텝 입력 형식을 확인해 주세요.") from exc


@router.post("/nc/confirm")
async def manual_nc(request: Request):
    try:
        async with request.form(max_files=1, max_fields=1) as form:
            payload = form.get("payload")
            if not isinstance(payload, str) or len(payload) > 2 * 1024 * 1024:
                raise CamInputError("NC 확인 요청을 확인해 주세요.")
            dto = ManualNcRequest.model_validate(json.loads(payload))
            if set(form.keys()) != {"payload", f"file:{dto.fileId}"} or len(form.multi_items()) != 2:
                raise CamInputError("NC 파일이 누락되거나 중복되었습니다.")
            file = form.get(f"file:{dto.fileId}")
            if not isinstance(file, UploadFile):
                raise CamInputError("NC 원본이 필요합니다.")
            data = await file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(413, "파일당 8 MiB 제한을 초과했습니다.")
            return await run_in_threadpool(confirm_nc, dto, data)
    except (ValidationError, CamInputError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, CamInputError) else "NC 확인 요청 형식이 올바르지 않습니다.") from exc


@router.post("/workplans/complete")
def complete_missing(request: CompletionRequest):
    try:
        return complete_workplan(request)
    except CamInputError as exc:
        raise HTTPException(422, str(exc)) from exc


async def nc_request(request, compile=False):
    try:
        async with request.form(max_files=1, max_fields=1) as form:
            payload = form.get("payload")
            if not isinstance(payload, str) or len(payload) > 2 * 1024 * 1024:
                raise CamInputError("NC 요청 정보를 확인해 주세요.")
            dto = (NcToolsRequest if compile else NcAnalyzeRequest).model_validate(json.loads(payload))
            if set(form.keys()) != {"payload", f"file:{dto.fileId}"} or len(form.multi_items()) != 2:
                raise CamInputError("NC 파일 파트가 누락되거나 중복되었습니다.")
            file = form.get(f"file:{dto.fileId}")
            if not isinstance(file, UploadFile):
                raise CamInputError("NC 원본 파일이 필요합니다.")
            data = await file.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise HTTPException(413, "파일당 8 MiB 제한을 초과했습니다.")
            return await run_in_threadpool(compile_tools, dto, data) if compile else await run_in_threadpool(analyze_nc, data, dto.fileId, dto.encoding)
    except (ValidationError, CamInputError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, CamInputError) else "NC 요청 형식이 올바르지 않습니다.") from exc


@router.post("/nc/analyze")
async def nc_analyze(request: Request):
    return await nc_request(request)


@router.post("/nc/tools")
async def nc_tools(request: Request):
    return await nc_request(request, compile=True)


@router.get("/schema")
def schema(request: Request, response: Response):
    catalog = get_catalog()
    etag = '"' + catalog["schemaHash"] + ":" + catalog["rulesVersion"] + ":" + catalog["referencePolicyHash"] + '"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"
    return catalog


@router.post("/review")
def review(request: PartialReviewRequest):
    return preview_assets(request.draft, request.targetAssetNodeIds)


@router.post("/cam/parse", summary="CAM JSON을 저장 없이 워킹스텝 초안으로 파싱")
async def parse_cam_files(request: Request):
    try:
        async with request.form(max_files=51, max_fields=1) as form:
            payload = form.get("payload")
            if not isinstance(payload, str) or len(payload) > 65536:
                raise CamInputError("payload JSON이 없거나 너무 큽니다.")
            dto = CamParseRequest.model_validate(json.loads(payload))
            expected = {"payload", *(f"file:{file_id}" for file_id in dto.orderedFileIds)}
            if dto.mappingFileId:
                expected.add(f"file:{dto.mappingFileId}")
            if set(form.keys()) != expected or len(form.multi_items()) != len(expected):
                raise CamInputError("파일 파트가 누락되었거나 중복되었습니다.")
            files, mapping = {}, None
            for key, upload in form.multi_items():
                if key == "payload":
                    continue
                if not isinstance(upload, UploadFile):
                    raise CamInputError("파일 파트 형식을 확인해 주세요.")
                data = await upload.read(MAX_FILE_BYTES + 1)
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(413, "파일당 8 MiB 제한을 초과했습니다.")
                file_id = key.removeprefix("file:")
                if file_id == dto.mappingFileId:
                    mapping = data
                else:
                    files[file_id] = ((upload.filename or "CAM.json")[:512], data)
            return await run_in_threadpool(parse_cam, dto, files, mapping)
    except ValidationError as exc:
        raise HTTPException(422, {"message": "CAM 요청 형식을 확인해 주세요.", "errors": exc.errors(include_context=False)}) from exc
    except (CamInputError, json.JSONDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
