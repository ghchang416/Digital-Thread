"""Bounded, ephemeral Access inspection. Never imports draft or persistence services."""
from concurrent.futures import Future, ThreadPoolExecutor
from copy import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import tempfile
import threading
import time

from .reader import AccessReadError, AccessReader
from .source_catalog import SourceCatalog


UPLOAD_BODY_LIMIT = 128 * 1024 * 1024 + 64 * 1024
PAGE_BYTES = 512 * 1024
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
REQUEST_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class SessionError(ValueError):
    def __init__(self, code: str, status: int = 400):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass(frozen=True)
class SessionLimits:
    sessions: int = 4
    readers: int = 1
    disk_bytes: int = 768 * 1024 * 1024
    ttl_seconds: float = 900
    sweep_seconds: float = 5

    def __post_init__(self):
        if not (1 <= self.sessions <= 4 and self.readers == 1 and 0 < self.disk_bytes <= 768 * 1024 * 1024
                and 0 < self.ttl_seconds <= 900 and 0 < self.sweep_seconds <= 5):
            raise ValueError("Invalid ELS session limits")


@dataclass
class _Session:
    import_id: str
    token_hash: bytes
    request_id: str
    path: Path
    expires: float
    expires_at: str
    state: str = "uploading"
    source_name: str = ""
    size: int = 0
    reserved: bool = True
    cancelled: threading.Event = field(default_factory=threading.Event)
    future: Future | None = None
    catalog: SourceCatalog | None = None
    error: str | None = None


def _bounded_page(items, *, cursor=None, page_size=50, key):
    if type(page_size) is not int or not 1 <= page_size <= 100:
        raise SessionError("INVALID_PAGE")
    start = 0
    if cursor is not None:
        positions = [i for i, item in enumerate(items) if item[key] == cursor]
        if len(positions) != 1:
            raise SessionError("INVALID_CURSOR")
        start = positions[0] + 1
    output, size = [], 0
    for item in items[start:start + page_size]:
        encoded = json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        length = len(encoded.encode("utf-8"))
        if size + length > PAGE_BYTES:
            if not output:
                raise SessionError("SOURCE_ITEM_TOO_LARGE", 422)
            break
        output.append(json.loads(encoded))
        size += length
    return {"items": output, "total": len(items),
            "nextCursor": output[-1][key] if output and start + len(output) < len(items) else None}


class ImportSessions:
    """One process owns a private root; other workers fail closed, never split sessions.

    Capacity is reserved before multipart parsing for parser spool + source + reader
    copy. A root lease bounds usage across processes sharing the same temp directory.
    """
    def __init__(self, root=None, *, reader=None, limits=None, clock=time.monotonic):
        self.reader = reader or AccessReader()
        self.limits = limits or SessionLimits()
        self.clock = clock
        self.root = Path(root or os.environ.get("ELS_IMPORT_TEMP_ROOT", Path(tempfile.gettempdir()) / "dt-creator-els-imports"))
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.root.is_symlink() or self.root.stat().st_uid != os.getuid() or self.root.stat().st_mode & 0o077:
            raise SessionError("IMPORT_STORE_UNSAFE", 503)
        self._lease = os.fdopen(os.open(self.root / ".owner.lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "r+")
        try:
            fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._lease.close()
            raise SessionError("IMPORT_STORE_BUSY", 503) from None
        self._lock = threading.RLock()
        self._sessions = {}
        self._closed = False
        self._stopped = threading.Event()
        try:
            self._clean_abandoned()
            self._lease.seek(0)
            self._lease.truncate()
            json.dump({"kind": "dt-els-owner-v1", "pid": os.getpid()}, self._lease)
            self._lease.flush()
            self._executor = ThreadPoolExecutor(max_workers=self.limits.readers, thread_name_prefix="els-read")
            self._sweeper = threading.Thread(target=self._sweep, name="els-expiry", daemon=True)
            self._sweeper.start()
        except BaseException:
            self._lease.close()
            raise

    def _clean_abandoned(self):
        # Holding the root lease proves the previous owner is no longer active.
        for directory in self.root.glob("session-*"):
            if directory.is_symlink() or not directory.is_dir() or not ID_PATTERN.fullmatch(directory.name[8:]):
                continue
            marker = directory / "lease.json"
            try:
                if marker.is_symlink() or marker.stat().st_size > 1024:
                    continue
                lease = json.loads(marker.read_text())
                if lease.get("kind") != "dt-els-session-v1" or lease.get("importId") != directory.name[8:]:
                    continue
            except (OSError, ValueError):
                continue
            shutil.rmtree(directory)

    def reserve(self, request_id: str):
        if not REQUEST_PATTERN.fullmatch(request_id):
            raise SessionError("INVALID_REQUEST_ID", 422)
        with self._lock:
            if self._closed:
                raise SessionError("IMPORT_STORE_CLOSED", 503)
            if len(self._sessions) >= self.limits.sessions:
                raise SessionError("IMPORT_SESSION_LIMIT", 429)
            reservation = 3 * self.reader.limits.file_bytes
            reserved = sum(s.reserved for s in self._sessions.values()) * reservation
            if reserved + reservation > self.limits.disk_bytes:
                raise SessionError("IMPORT_DISK_LIMIT", 429)
            # Leave space for unrelated temporary files instead of relying on a logical cap alone.
            if shutil.disk_usage(self.root).free < reservation:
                raise SessionError("IMPORT_DISK_LIMIT", 503)
            import_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
            path = self.root / ("session-" + import_id)
            path.mkdir(mode=0o700)
            expires_at = datetime.fromtimestamp(time.time() + self.limits.ttl_seconds, timezone.utc).isoformat()
            try:
                (path / "lease.json").write_text(json.dumps({"kind": "dt-els-session-v1", "importId": import_id,
                    "pid": os.getpid(), "expiresAt": expires_at}))
                (path / "source.access").touch(mode=0o600, exist_ok=False)
            except BaseException:
                shutil.rmtree(path)
                raise
            self._sessions[import_id] = _Session(import_id, hashlib.sha256(token.encode()).digest(), request_id,
                                                path, self.clock() + self.limits.ttl_seconds, expires_at)
            return import_id, token

    def _get(self, import_id, token, *, allow_expired=False):
        if not ID_PATTERN.fullmatch(import_id) or not TOKEN_PATTERN.fullmatch(token):
            raise SessionError("IMPORT_NOT_FOUND", 404)
        session = self._sessions.get(import_id)
        if session is None or not hmac.compare_digest(session.token_hash, hashlib.sha256(token.encode()).digest()):
            raise SessionError("IMPORT_NOT_FOUND", 404)
        if not allow_expired and (session.expires <= self.clock() or session.cancelled.is_set()):
            raise SessionError("IMPORT_NOT_FOUND", 404)
        return session

    def append(self, import_id, token, chunk: bytes):
        with self._lock:
            session = self._get(import_id, token)
            if session.state != "uploading":
                raise SessionError("IMPORT_STATE_CONFLICT", 409)
            if session.size + len(chunk) > self.reader.limits.file_bytes:
                raise SessionError("FILE_TOO_LARGE", 413)
            with (session.path / "source.access").open("ab") as target:
                target.write(chunk)
            session.size += len(chunk)

    def submit(self, import_id, token, filename):
        name = (filename or "").replace("\\", "/").split("/")[-1]
        if not name or len(name) > 255 or any(ord(c) < 32 for c in name) or Path(name).suffix.lower() not in {".mdb", ".accdb"}:
            raise SessionError("UNSUPPORTED_ACCESS_FILENAME", 422)
        with self._lock:
            session = self._get(import_id, token)
            if session.state != "uploading":
                raise SessionError("IMPORT_STATE_CONFLICT", 409)
            with (session.path / "source.access").open("rb") as source:
                header = source.read(32)
            if session.size < 2048 or not header.startswith((b"\x00\x01\x00\x00Standard Jet DB\x00", b"\x00\x01\x00\x00Standard ACE DB\x00")):
                raise SessionError("UNSUPPORTED_ACCESS", 422)
            session.source_name, session.state = name, "queued"
            session.future = self._executor.submit(self._read, session)
            return self._status(session)

    def _read(self, session):
        try:
            with self._lock:
                if session.cancelled.is_set():
                    return
                session.state = "reading"
            with (session.path / "source.access").open("rb") as source:
                reader = copy(self.reader)
                reader.temp_root = session.path
                snapshot = reader.read(source, cancelled=session.cancelled)
            if session.cancelled.is_set():
                return
            catalog = SourceCatalog(snapshot)
            with self._lock:
                if not session.cancelled.is_set():
                    session.catalog, session.state = catalog, "ready"
        except AccessReadError as exc:
            with self._lock:
                session.state, session.error = "failed", exc.code
        except Exception:
            # Do not expose source cells, paths, connection strings or exception messages.
            with self._lock:
                session.state, session.error = "failed", "IMPORT_READ_FAILED"
        finally:
            with self._lock:
                (session.path / "source.access").unlink(missing_ok=True)
                session.reserved = False

    def _status(self, session):
        result = dict(importId=session.import_id, requestId=session.request_id, status=session.state,
                      expiresAt=session.expires_at, sourceName=session.source_name, size=session.size,
                      errorCode=session.error, persisted=False)
        if session.catalog:
            snapshot = session.catalog.snapshot
            result.update(sourceSha256=snapshot.sha256, format=snapshot.format, readerVersion=snapshot.reader_version,
                          operationCount=len(session.catalog.operations), diagnosticCount=len(session.catalog.diagnostics),
                          tables=[dict(name=t.name, rowCount=len(t.rows), columnCount=len(t.columns), primaryKey=t.primary_key)
                                  for t in snapshot.tables.values()])
        return json.loads(json.dumps(result))

    def status(self, import_id, token):
        with self._lock:
            return self._status(self._get(import_id, token))

    def _catalog(self, import_id, token):
        session = self._get(import_id, token)
        if session.state != "ready":
            raise SessionError("IMPORT_NOT_READY", 409)
        return session.catalog

    def operations(self, import_id, token, *, search="", cursor=None, page_size=50):
        if not isinstance(search, str) or len(search) > 256:
            raise SessionError("INVALID_SEARCH", 422)
        with self._lock:
            catalog = self._catalog(import_id, token)
            fields = ("partNo", "partRevision", "opNo", "partName", "machineCode", "machineNumber")
            items = [op for op in catalog.operations if search.casefold() in
                     " ".join(str(op.get(k) or "") for k in fields).casefold()]
            return _bounded_page(items, cursor=cursor, page_size=page_size, key="operationKey")

    def operation(self, import_id, token, operation_key, *, cursor=None, page_size=50):
        with self._lock:
            catalog = self._catalog(import_id, token)
            detail = catalog.details.get(operation_key)
            if detail is None:
                raise SessionError("OPERATION_NOT_FOUND", 404)
            programs = [{k: p[k] for k in ("programKey", "pgmNo", "revision", "selectable")} |
                        {"rowCount": len(p["rows"])} for p in detail["programs"]]
            summary = {k: v for k, v in detail.items() if k not in {"programs", "issues"}}
            result = dict(operation=summary, programs=_bounded_page(programs, cursor=cursor, page_size=page_size, key="programKey"),
                          issueCount=len(detail["issues"]), issues=detail["issues"][:100])
            return json.loads(json.dumps(result, ensure_ascii=False))

    def rows(self, import_id, token, operation_key, program_key, *, cursor=None, page_size=50):
        with self._lock:
            detail = self._catalog(import_id, token).details.get(operation_key)
            if detail is None:
                raise SessionError("OPERATION_NOT_FOUND", 404)
            programs = [p for p in detail["programs"] if p["programKey"] == program_key]
            if len(programs) != 1:
                raise SessionError("PROGRAM_NOT_FOUND", 404)
            return _bounded_page(programs[0]["rows"], cursor=cursor, page_size=page_size, key="rowId")

    def diagnostics(self, import_id, token, *, cursor=None, page_size=50):
        with self._lock:
            items = [dict(diagnosticId=str(i), **item) for i, item in enumerate(self._catalog(import_id, token).diagnostics)]
            return _bounded_page(items, cursor=cursor, page_size=page_size, key="diagnosticId")

    def source_context(self, import_id, token, operation_key, program_key):
        from .selection import source_context
        with self._lock:
            catalog = self._catalog(import_id, token)
            context = source_context(catalog, operation_key, program_key)
            context["sourceName"] = self._get(import_id, token).source_name
            return context

    def delete(self, import_id, token):
        with self._lock:
            session = self._get(import_id, token)
            session.cancelled.set()
        self._dispose(session)

    def abort_upload(self, import_id, token):
        with self._lock:
            session = self._get(import_id, token, allow_expired=True)
            session.cancelled.set()
        self._dispose(session)

    def _dispose(self, session):
        session.cancelled.set()
        if session.future:
            session.future.cancel()
            if not session.future.cancelled():
                try:
                    session.future.result()
                except Exception:
                    pass  # Cleanup must also run after an unexpected worker failure.
        with self._lock:
            if self._sessions.pop(session.import_id, None) is not None:
                shutil.rmtree(session.path)
                session.catalog = None

    def expire(self):
        with self._lock:
            sessions = [s for s in self._sessions.values() if s.expires <= self.clock()]
            for session in sessions:
                session.cancelled.set()
        for session in sessions:
            # An in-flight multipart spool still holds its reservation until route cleanup.
            if session.state != "uploading":
                self._dispose(session)

    def _sweep(self):
        while not self._stopped.wait(self.limits.sweep_seconds):
            self.expire()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stopped.set()
            sessions = list(self._sessions.values())
            for session in sessions:
                session.cancelled.set()
        self._sweeper.join()
        self._executor.shutdown(wait=True, cancel_futures=True)
        for session in sessions:
            self._dispose(session)
        self._lease.close()
