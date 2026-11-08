"""ELS inspection routes. New paths only; existing drafts and APIs are untouched."""
import asyncio
import atexit
import os
import threading

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import ClientDisconnect
from python_multipart.exceptions import MultipartParseError

from src.schemas.creator_els_sessions import ElsImportAccepted, ElsImportStatus, ElsOperationDetail, ElsSourcePage
from src.services.creator.els.reader import AccessReader
from src.services.creator.els.sessions import ImportSessions, SessionError
from src.schemas.creator_els import ElsBuildRequest, ElsCandidate, ElsConfirmRequest, ElsReviewRequest, ElsCompleteRequest


router = APIRouter(prefix="/els", tags=["ELS inspection"])
_manager = None
_manager_lock = threading.Lock()


def get_sessions():
    global _manager
    if os.environ.get("CREATOR_ELS_ENABLED") != "1":
        raise HTTPException(503, "ELS_INSPECTION_DISABLED")
    if not AccessReader().available():
        raise HTTPException(503, "READER_UNAVAILABLE")
    try:
        with _manager_lock:
            if _manager is None:
                _manager = ImportSessions()
            return _manager
    except (OSError, SessionError) as exc:
        raise HTTPException(503, exc.code if isinstance(exc, SessionError) else "IMPORT_STORE_UNAVAILABLE") from None


def close_sessions():
    global _manager
    with _manager_lock:
        if _manager is not None:
            _manager.close()
            _manager = None


atexit.register(close_sessions)
router.add_event_handler("shutdown", close_sessions)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except SessionError as exc:
        raise HTTPException(exc.status, exc.code) from None
    except OSError:
        raise HTTPException(503, "IMPORT_STORAGE_UNAVAILABLE") from None


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


class _ImportMultipartParser(MultiPartParser):
    finished = False

    def on_end(self):
        self.finished = True
        super().on_end()

    async def parse(self):
        try:
            form = await super().parse()
            if not self.finished:
                raise MultiPartException("Incomplete multipart upload")
            return form
        except BaseException:
            # A truncated final chunk can leave a file outside FormData.items.
            for file in self._files_to_close_on_error:
                file.close()
            raise


@router.post("/imports", status_code=202, response_model=ElsImportAccepted,
             dependencies=[Depends(no_store)], openapi_extra={"requestBody": {"required": True, "content": {
                 "multipart/form-data": {"schema": {"type": "object", "required": ["file"],
                     "properties": {"file": {"type": "string", "format": "binary"}}}}}}})
async def upload(request: Request, request_id: str = Header(default="", alias="X-ELS-Request-Id"),
                 sessions: ImportSessions = Depends(get_sessions)):
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
        raise HTTPException(415, "MULTIPART_REQUIRED")
    # Register cleanup before the first cancellable await; otherwise a cancelled
    # threadpool reservation could leave an uploading lease with no owning request.
    import_id, token = _call(sessions.reserve, request_id)
    accepted = False
    try:
        async def receive_file():
            form = await _ImportMultipartParser(request.headers, request.stream(), max_files=1, max_fields=0).parse()
            try:
                if list(form.keys()) != ["file"] or len(form.multi_items()) != 1:
                    raise HTTPException(422, "ONE_ACCESS_FILE_REQUIRED")
                source = form.get("file")
                if not isinstance(source, UploadFile):
                    raise HTTPException(422, "ONE_ACCESS_FILE_REQUIRED")
                while chunk := await source.read(1024 * 1024):
                    await run_in_threadpool(_call, sessions.append, import_id, token, chunk)
                return await run_in_threadpool(_call, sessions.submit, import_id, token, source.filename)
            finally:
                await form.close()
        result = await asyncio.wait_for(receive_file(), timeout=120)
        accepted = True
        return {**result, "ownerToken": token}
    except asyncio.TimeoutError:
        raise HTTPException(408, "IMPORT_UPLOAD_TIMEOUT") from None
    except ClientDisconnect:
        raise HTTPException(400, "IMPORT_UPLOAD_DISCONNECTED") from None
    except (MultiPartException, MultipartParseError):
        raise HTTPException(400, "INVALID_ACCESS_MULTIPART") from None
    finally:
        if not accepted:
            with anyio.CancelScope(shield=True):
                await run_in_threadpool(sessions.abort_upload, import_id, token)


@router.get("/imports/{import_id}", response_model=ElsImportStatus, dependencies=[Depends(no_store)])
def status(import_id: str, owner: str = Header(default="", alias="X-ELS-Owner-Token"),
           sessions: ImportSessions = Depends(get_sessions)):
    return _call(sessions.status, import_id, owner)


@router.get("/imports/{import_id}/operations", response_model=ElsSourcePage, dependencies=[Depends(no_store)])
def operations(import_id: str, owner: str = Header(default="", alias="X-ELS-Owner-Token"),
               search: str = Query(default="", max_length=256), cursor: str | None = Query(default=None, max_length=128),
               page_size: int = Query(default=50, ge=1, le=100, alias="pageSize"), sessions: ImportSessions = Depends(get_sessions)):
    return _call(sessions.operations, import_id, owner, search=search, cursor=cursor, page_size=page_size)


@router.get("/imports/{import_id}/operations/{operation_key}", response_model=ElsOperationDetail, dependencies=[Depends(no_store)])
def operation(import_id: str, operation_key: str, owner: str = Header(default="", alias="X-ELS-Owner-Token"),
              cursor: str | None = Query(default=None, max_length=128), page_size: int = Query(default=50, ge=1, le=100, alias="pageSize"),
              sessions: ImportSessions = Depends(get_sessions)):
    return _call(sessions.operation, import_id, owner, operation_key, cursor=cursor, page_size=page_size)


@router.get("/imports/{import_id}/operations/{operation_key}/programs/{program_key}/rows",
            response_model=ElsSourcePage, dependencies=[Depends(no_store)])
def rows(import_id: str, operation_key: str, program_key: str, owner: str = Header(default="", alias="X-ELS-Owner-Token"),
         cursor: str | None = Query(default=None, max_length=128), page_size: int = Query(default=50, ge=1, le=100, alias="pageSize"),
         sessions: ImportSessions = Depends(get_sessions)):
    return _call(sessions.rows, import_id, owner, operation_key, program_key, cursor=cursor, page_size=page_size)


@router.get("/imports/{import_id}/diagnostics", response_model=ElsSourcePage, dependencies=[Depends(no_store)])
def diagnostics(import_id: str, owner: str = Header(default="", alias="X-ELS-Owner-Token"),
                cursor: str | None = Query(default=None, max_length=128), page_size: int = Query(default=50, ge=1, le=100, alias="pageSize"),
                sessions: ImportSessions = Depends(get_sessions)):
    return _call(sessions.diagnostics, import_id, owner, cursor=cursor, page_size=page_size)


@router.delete("/imports/{import_id}", status_code=204, dependencies=[Depends(no_store)])
def cancel(import_id: str, owner: str = Header(default="", alias="X-ELS-Owner-Token"),
           sessions: ImportSessions = Depends(get_sessions)):
    _call(sessions.delete, import_id, owner)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


def _els_call(function, *args):
    try:
        return _call(function, *args)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(422, code if code.startswith("ELS_") and len(code) <= 256 else "ELS_INPUT_INVALID") from None


@router.get("/imports/{import_id}/operations/{operation_key}/programs/{program_key}/source", dependencies=[Depends(no_store)])
def source_selection(import_id: str, operation_key: str, program_key: str,
                     owner: str = Header(default="", alias="X-ELS-Owner-Token"), sessions: ImportSessions = Depends(get_sessions)):
    return _els_call(sessions.source_context, import_id, owner, operation_key, program_key)


@router.post("/imports/{import_id}/prepare", dependencies=[Depends(no_store)])
def prepare_candidate(import_id: str, request: ElsBuildRequest, owner: str = Header(default="", alias="X-ELS-Owner-Token"),
                      sessions: ImportSessions = Depends(get_sessions)):
    from src.services.creator.els.build import prepare
    if import_id != request.request.importId:
        raise HTTPException(422, "ELS_IMPORT_SCOPE")
    source = _els_call(sessions.source_context, import_id, owner, request.operationKey, request.programKey)
    candidate = _els_call(prepare, source, request)
    targets = [a.assetNodeId for a in candidate.draft.assets if request.request.mode == "replace-project" or
               a.assetNodeId not in {a.assetNodeId for a in request.baseDraft.assets}]
    checks = [_els_call(review_preparation, candidate, asset_id) for asset_id in targets]
    _call(sessions.status, import_id, owner)  # Discard late responses from cancelled/expired sessions.
    return dict(candidate=candidate.model_dump(by_alias=True), ready=all(c["valid"] for c in checks),
                checks=checks, confirmationRequired=bool(candidate.metadata.elsWorkplans), persisted=False)


def review_preparation(candidate, asset_id):
    from src.services.creator.els.review import review
    result = review(candidate, [asset_id], require_confirmation=False)
    # Preparation diagnostics are not a download endpoint or an ELS confirmation.
    return dict(assetNodeId=asset_id, valid=result["valid"], issues=result["issues"], warnings=result["warnings"],
                pendingStorage=result.get("pendingStorage", []))


@router.post("/confirm", response_model=ElsCandidate, dependencies=[Depends(no_store)])
def confirm_candidate(request: ElsConfirmRequest):
    from src.services.creator.els.review import confirm
    return _els_call(confirm, request)


@router.post("/review", dependencies=[Depends(no_store)])
def review_candidate(request: ElsReviewRequest):
    from src.services.creator.els.review import review
    return _els_call(review, request.candidate, request.targetAssetNodeIds)


@router.post("/complete", response_model=ElsCandidate, dependencies=[Depends(no_store)])
def complete_candidate(request: ElsCompleteRequest):
    from src.services.creator.els.complete import complete
    return _els_call(complete, request)
