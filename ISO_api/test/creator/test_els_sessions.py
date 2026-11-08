"""Ephemeral ELS API tests. No MongoDB, live endpoints, or user drafts are used."""
from copy import deepcopy
import hashlib
import json
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.apis.v3.creator_els import router, get_sessions
from src.apis.v3.creator_middleware import BodyLimitMiddleware
from src.apis.v3 import creator_middleware
from src.services.creator.els.reader import AccessReader, AccessReadError, ReaderLimits
from src.services.creator.els.sessions import ImportSessions, SessionError, SessionLimits, _bounded_page
from test_els_source_catalog import snapshot


ACCESS = b"\x00\x01\x00\x00Standard Jet DB\x00" + b"\x00" * 2048


class FakeReader:
    def __init__(self, *, blocked=False, fail=None):
        self.limits = ReaderLimits(file_bytes=4096)
        self.started, self.release, self.finished = threading.Event(), threading.Event(), threading.Event()
        self.fail = fail
        if not blocked:
            self.release.set()

    def read(self, source, *, cancelled):
        self.started.set()
        raw = source.read()
        try:
            while not self.release.wait(.01):
                if cancelled.is_set():
                    raise AccessReadError("IMPORT_CANCELLED")
            if self.fail:
                raise self.fail
            value = snapshot()
            value.sha256, value.size = hashlib.sha256(raw).hexdigest(), len(raw)
            return value
        finally:
            self.finished.set()


@pytest.fixture
def sessions(tmp_path):
    manager = ImportSessions(tmp_path / "imports", reader=FakeReader())
    yield manager
    manager.close()


@pytest.fixture
def client(sessions):
    app = FastAPI()
    app.include_router(router, prefix="/api/v3/creator")
    app.add_middleware(BodyLimitMiddleware)
    app.dependency_overrides[get_sessions] = lambda: sessions
    with TestClient(app) as test_client:
        yield test_client


def submit(manager, request_id="request1"):
    import_id, token = manager.reserve(request_id)
    manager.append(import_id, token, ACCESS)
    manager.submit(import_id, token, "source.mdb")
    return import_id, token


def ready(manager, import_id):
    manager._sessions[import_id].future.result(timeout=5)


def upload(client):
    response = client.post("/api/v3/creator/els/imports", headers={"X-ELS-Request-Id": "request1"},
                           files={"file": ("source.mdb", ACCESS)})
    assert response.status_code == 202, response.text
    return response.json()


def test_session_read_is_non_mutating_paged_and_removes_original_bytes(sessions):
    import_id, token = submit(sessions)
    ready(sessions, import_id)
    result = sessions.status(import_id, token)
    assert result["status"] == "ready" and result["persisted"] is False
    assert result["sourceSha256"] == hashlib.sha256(ACCESS).hexdigest()
    assert "ownerToken" not in result
    assert not list(sessions.root.rglob("source.access"))
    first = sessions.operations(import_id, token, page_size=1)
    second = sessions.operations(import_id, token, cursor=first["nextCursor"], page_size=1)
    assert first["items"][0]["operationKey"] != second["items"][0]["operationKey"]
    op = next(o for o in sessions.operations(import_id, token)["items"] if o["opNo"] == "010" and o["partRevision"] == "01")
    detail = sessions.operation(import_id, token, op["operationKey"], page_size=1)
    assert detail["programs"]["total"] == 2
    program = detail["programs"]["items"][0]
    assert "rows" not in program and program["revision"] == "A"
    first_row = sessions.rows(import_id, token, op["operationKey"], program["programKey"], page_size=1)
    assert first_row["items"][0]["sourceSN"] == 2
    second_row = sessions.rows(import_id, token, op["operationKey"], program["programKey"], cursor=first_row["nextCursor"])
    assert second_row["items"][0]["sourceSN"] == 1
    first_row["items"][0]["values"]["TOOLNO"] = "CHANGED"
    assert sessions.rows(import_id, token, op["operationKey"], program["programKey"])["items"][0]["values"]["TOOLNO"] == "001"


@pytest.mark.parametrize("token", ["", "guess", "a" * 43, "../owner"])
def test_owner_token_is_required_for_every_action(sessions, token):
    import_id, owner = submit(sessions)
    ready(sessions, import_id)
    for action in (sessions.status, sessions.operations, sessions.diagnostics, sessions.delete):
        with pytest.raises(SessionError, match="IMPORT_NOT_FOUND") as error:
            action(import_id, token)
        assert error.value.status == 404
    assert sessions.status(import_id, owner)["status"] == "ready"


def test_other_session_owner_cannot_read_or_cancel(sessions):
    first, token = submit(sessions)
    second, other = submit(sessions, "request2")
    ready(sessions, first)
    ready(sessions, second)
    with pytest.raises(SessionError, match="IMPORT_NOT_FOUND"):
        sessions.delete(first, other)
    with pytest.raises(SessionError, match="IMPORT_NOT_FOUND"):
        sessions.status(second, token)


def test_cancel_waits_for_reader_and_fully_cleans_directory(tmp_path):
    reader = FakeReader(blocked=True)
    manager = ImportSessions(tmp_path, reader=reader)
    try:
        import_id, token = submit(manager)
        assert reader.started.wait(1)
        with pytest.raises(SessionError, match="IMPORT_NOT_READY"):
            manager.operations(import_id, token)
        manager.delete(import_id, token)
        assert reader.finished.is_set()
        assert not manager._sessions and not list(tmp_path.glob("session-*"))
        with pytest.raises(SessionError, match="IMPORT_NOT_FOUND"):
            manager.status(import_id, token)
    finally:
        manager.close()


def test_cancel_queued_job_does_not_start_second_reader(tmp_path):
    reader = FakeReader(blocked=True)
    manager = ImportSessions(tmp_path, reader=reader)
    try:
        first, owner = submit(manager)
        assert reader.started.wait(1)
        second, other = submit(manager, "second")
        assert manager.status(second, other)["status"] == "queued"
        manager.delete(second, other)
        assert not reader.finished.is_set()
        manager.delete(first, owner)
    finally:
        manager.close()


def test_ttl_cancels_read_and_upload_reservation_stays_until_route_cleanup(tmp_path):
    clock = [0]
    reader = FakeReader(blocked=True)
    manager = ImportSessions(tmp_path, reader=reader, clock=lambda: clock[0], limits=SessionLimits(ttl_seconds=10))
    try:
        import_id, token = submit(manager)
        assert reader.started.wait(1)
        uploading, owner = manager.reserve("uploading")
        clock[0] = 11
        manager.expire()
        assert reader.finished.is_set() and import_id not in manager._sessions
        assert manager._sessions[uploading].reserved
        with pytest.raises(SessionError, match="IMPORT_NOT_FOUND"):
            manager.append(uploading, owner, b"more")
        manager.abort_upload(uploading, owner)
        assert not manager._sessions
    finally:
        manager.close()


def test_automatic_expiry_runs_without_more_http_requests(tmp_path):
    manager = ImportSessions(tmp_path, reader=FakeReader(), limits=SessionLimits(ttl_seconds=.08, sweep_seconds=.01))
    try:
        import_id, _ = submit(manager)
        ready(manager, import_id)
        deadline = time.monotonic() + 2
        while (manager._sessions or list(tmp_path.glob("session-*"))) and time.monotonic() < deadline:
            time.sleep(.01)
        assert not manager._sessions and not list(tmp_path.glob("session-*"))
    finally:
        manager.close()


def test_session_and_disk_budgets_are_reserved_before_upload(tmp_path):
    reader = FakeReader(blocked=True)
    manager = ImportSessions(tmp_path, reader=reader, limits=SessionLimits(sessions=2, disk_bytes=3 * 4096))
    try:
        first, token = manager.reserve("first")
        with pytest.raises(SessionError, match="IMPORT_DISK_LIMIT"):
            manager.reserve("second")
        manager.abort_upload(first, token)
        first, token = submit(manager)
        reader.release.set()
        ready(manager, first)
        second, _ = manager.reserve("second")
        with pytest.raises(SessionError, match="IMPORT_SESSION_LIMIT"):
            manager.reserve("third")
        assert second in manager._sessions
    finally:
        manager.close()


def test_second_owner_cannot_clear_active_sessions_and_abandoned_cleanup_is_scoped(tmp_path):
    first = ImportSessions(tmp_path, reader=FakeReader())
    import_id, token = first.reserve("first")
    with pytest.raises(SessionError, match="IMPORT_STORE_BUSY"):
        ImportSessions(tmp_path, reader=FakeReader())
    assert first.status(import_id, token)["status"] == "uploading"
    first.close()
    abandoned = tmp_path / ("session-" + "a" * 32)
    abandoned.mkdir()
    (abandoned / "lease.json").write_text(json.dumps({"kind": "dt-els-session-v1", "importId": "a" * 32}))
    (abandoned / "source.access").write_bytes(ACCESS)
    unrelated = tmp_path / ("session-" + "b" * 32)
    unrelated.mkdir()
    (unrelated / "lease.json").write_text('{"kind":"someone-else"}')
    second = ImportSessions(tmp_path, reader=FakeReader())
    try:
        assert not abandoned.exists() and unrelated.exists()
    finally:
        second.close()


@pytest.mark.parametrize("failure,code", [(AccessReadError("UNSUPPORTED_ACCESS_FORMAT"), "UNSUPPORTED_ACCESS_FORMAT"),
                                         (RuntimeError("secret /server/path connection-string"), "IMPORT_READ_FAILED")])
def test_failed_read_is_sanitized_and_releases_disk(tmp_path, failure, code):
    manager = ImportSessions(tmp_path, reader=FakeReader(fail=failure))
    try:
        import_id, token = submit(manager)
        ready(manager, import_id)
        state = manager.status(import_id, token)
        assert state["status"] == "failed" and state["errorCode"] == code
        assert "secret" not in json.dumps(state) and not manager._sessions[import_id].reserved
        assert not list(tmp_path.rglob("source.access"))
    finally:
        manager.close()


def test_upload_and_bounded_source_browsing_http(client, sessions):
    created = upload(client)
    import_id, token = created["importId"], created["ownerToken"]
    ready(sessions, import_id)
    url = "/api/v3/creator/els/imports/" + import_id
    headers = {"X-ELS-Owner-Token": token}
    status = client.get(url, headers=headers)
    assert status.headers["cache-control"] == "no-store" and status.json()["status"] == "ready"
    assert token not in status.text
    assert client.get(url).status_code == 404
    assert client.get(url + "?ownerToken=" + token).status_code == 404
    assert client.get(url + "/operations", headers=headers, params={"pageSize": 101}).status_code == 422
    operations = client.get(url + "/operations", headers=headers).json()
    op = next(o for o in operations["items"] if o["opNo"] == "010" and o["partRevision"] == "01")
    detail_url = url + "/operations/" + op["operationKey"]
    detail = client.get(detail_url, headers=headers).json()
    pgm = detail["programs"]["items"][0]["programKey"]
    rows = client.get(detail_url + "/programs/" + pgm + "/rows", headers=headers).json()
    assert len(rows["items"]) == 2
    assert client.get(detail_url + "/programs/wrong/rows", headers=headers).status_code == 404
    assert client.get(url + "/diagnostics", headers=headers).json()["total"] == 0
    assert client.delete(url).status_code == 404
    assert client.delete(url, headers=headers).status_code == 204
    assert client.get(url, headers=headers).status_code == 404
    assert not sessions._sessions and not list(sessions.root.glob("session-*"))


@pytest.mark.parametrize("case,expected", [("invalid-request", 422), ("two-files", 400), ("wrong-field", 422),
    ("non-access", 422), ("bad-extension", 422), ("too-large-file", 413), ("not-multipart", 415), ("extra-field", 400)])
def test_bad_uploads_never_leave_session_or_file(client, sessions, case, expected):
    kwargs = dict(headers={"X-ELS-Request-Id": "req"}, files={"file": ("input.mdb", ACCESS)})
    if case == "invalid-request": kwargs["headers"] = {"X-ELS-Request-Id": "../bad"}
    if case == "two-files": kwargs["files"] = [("file", ("a.mdb", ACCESS)), ("file", ("b.mdb", ACCESS))]
    if case == "wrong-field": kwargs["files"] = {"other": ("a.mdb", ACCESS)}
    if case == "non-access": kwargs["files"] = {"file": ("a.mdb", b"not access")}
    if case == "bad-extension": kwargs["files"] = {"file": ("a.exe", ACCESS)}
    if case == "too-large-file": kwargs["files"] = {"file": ("a.mdb", ACCESS + b"x" * 4096)}
    if case == "not-multipart": kwargs = dict(json={"file": "anything"})
    if case == "extra-field": kwargs["data"] = {"requestId": "not-accepted-in-body"}
    response = client.post("/api/v3/creator/els/imports", **kwargs)
    assert response.status_code == expected, response.text
    assert not sessions._sessions and not list(sessions.root.glob("session-*"))


def test_upload_filename_is_only_display_metadata(client, sessions):
    response = client.post("/api/v3/creator/els/imports", headers={"X-ELS-Request-Id": "req"},
                           files={"file": ("C:\\private\\folder\\data.mdb", ACCESS)})
    assert response.status_code == 202
    assert response.json()["sourceName"] == "data.mdb"
    assert not list(sessions.root.rglob("data.mdb"))


def test_disabled_and_missing_reader_do_not_create_store(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v3/creator")
    client = TestClient(app)
    monkeypatch.delenv("CREATOR_ELS_ENABLED", raising=False)
    assert client.post("/api/v3/creator/els/imports").json()["detail"] == "ELS_INSPECTION_DISABLED"
    monkeypatch.setenv("CREATOR_ELS_ENABLED", "1")
    monkeypatch.setattr(AccessReader, "available", lambda _: False)
    result = client.post("/api/v3/creator/els/imports")
    assert result.status_code == 503 and result.json()["detail"] == "READER_UNAVAILABLE"


def test_page_byte_budget_never_silently_drops_rows_and_preserves_exact_data():
    items = [dict(rowId=str(i), values={"large": "x" * 240000, "z": 0, "b": False, "null": None, "empty": ""}) for i in range(3)]
    original = deepcopy(items)
    first = _bounded_page(items, key="rowId")
    assert len(first["items"]) == 2 and first["nextCursor"] == "1" and first["total"] == 3
    second = _bounded_page(items, cursor=first["nextCursor"], key="rowId")
    assert len(second["items"]) == 1 and second["nextCursor"] is None
    assert first["items"] + second["items"] == original and items == original
    with pytest.raises(SessionError, match="INVALID_CURSOR"):
        _bounded_page(items, cursor="elsewhere", key="rowId")


@pytest.mark.asyncio
async def test_streaming_limit_exact_path_and_legacy_limits_are_unchanged(monkeypatch):
    monkeypatch.setattr(creator_middleware, "UPLOAD_BODY_LIMIT", 10)
    calls = []

    async def downstream(scope, receive, send):
        calls.append(scope["path"])
        while True:
            msg = await receive()
            if not msg.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = BodyLimitMiddleware(downstream, limit=3)

    async def request(path, method="POST", headers=None):
        chunks = iter([{"type": "http.request", "body": b"123456", "more_body": True},
                       {"type": "http.request", "body": b"123456", "more_body": False}])
        messages = []
        async def receive(): return next(chunks)
        async def send(message): messages.append(message)
        await middleware({"type": "http", "path": path, "method": method, "headers": headers or []}, receive, send)
        return messages[0]["status"]

    assert await request("/api/v3/creator/els/imports") == 413
    assert calls == ["/api/v3/creator/els/imports"]  # Streaming, not pre-buffered.
    calls.clear()
    assert await request("/api/v3/creator/els/imports/other") == 413
    assert await request("/api/v3/creator/els/imports", "PUT") == 413
    assert not calls
    assert await request("/api/v3/creator/nc/analyze") == 204
    assert await request("/api/v3/creator/cam/parse") == 204
    assert await request("/api/v3/creator/nc/tools") == 204
    assert await request("/api/v3/creator/nc/confirm") == 413
    assert await request("/api/v3/assets") == 204
    assert await request("/api/v3/creator/els/imports", headers=[(b"content-length", b"11")]) == 413
    assert await request("/api/v3/creator/els/imports", headers=[(b"content-length", b"invalid")]) == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("ending", ["limit", "disconnect", "truncated"])
async def test_mid_multipart_disconnect_or_limit_closes_spools_and_session(sessions, monkeypatch, ending):
    from starlette import formparsers
    spools = []
    original = formparsers.SpooledTemporaryFile

    def tracked(*args, **kwargs):
        file = original(*args, **kwargs)
        spools.append(file)
        return file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked)
    monkeypatch.setattr(creator_middleware, "UPLOAD_BODY_LIMIT", 1024)
    app = FastAPI()
    app.include_router(router, prefix="/api/v3/creator")
    app.add_middleware(BodyLimitMiddleware)
    app.dependency_overrides[get_sessions] = lambda: sessions
    beginning = b'--test\r\nContent-Disposition: form-data; name="file"; filename="x.mdb"\r\nContent-Type: application/octet-stream\r\n\r\n'
    chunks = iter([{"type": "http.request", "body": beginning + b"x" * 512, "more_body": True},
                   {"type": "http.disconnect"} if ending == "disconnect" else
                   {"type": "http.request", "body": b"x" * (512 if ending == "limit" else 1), "more_body": False}])
    messages = []
    async def receive(): return next(chunks)
    async def send(message): messages.append(message)
    await app({"type": "http", "http_version": "1.1", "method": "POST", "scheme": "http",
               "path": "/api/v3/creator/els/imports", "query_string": b"",
               "headers": [(b"content-type", b"multipart/form-data; boundary=test"), (b"x-els-request-id", b"request")],
               "server": ("testserver", 80), "client": ("testclient", 123)}, receive, send)
    assert messages[0]["status"] == (413 if ending == "limit" else 400)
    assert spools and all(file.closed for file in spools)
    assert not sessions._sessions and not list(sessions.root.glob("session-*"))
