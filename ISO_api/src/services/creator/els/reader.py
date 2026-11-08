"""Bounded read-only Access adapter. No CreatorDraft, Mongo, or legacy API imports."""
from dataclasses import dataclass, field
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from typing import BinaryIO, Callable
import unicodedata


TABLES = frozenset({"part_info", "operation_info", "operation_machining", "machine_milling",
                    "tool_milling", "part_file", "machine_file", "tool_file"})
READER_VERSION = "jackcess-4.0.8/els-1"
VERIFIED_FORMATS = frozenset({"V2000", "V2010"})


class AccessReadError(ValueError):
    """Public diagnostics deliberately contain no uploaded values or server paths."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReaderLimits:
    file_bytes: int = 128 * 1024 * 1024
    output_bytes: int = 16 * 1024 * 1024
    line_bytes: int = 256 * 1024
    rows: int = 100000
    seconds: float = 60

    def __post_init__(self):
        if not (0 < self.file_bytes <= 128 * 1024 * 1024 and 0 < self.output_bytes <= 16 * 1024 * 1024
                and 0 < self.line_bytes <= 256 * 1024 and 0 < self.rows <= 100000
                and 0 < self.seconds <= 120):
            raise ValueError("Invalid reader limits")


@dataclass
class AccessTable:
    name: str
    columns: list[dict]
    primary_key: list[str]
    rows: list[dict] = field(default_factory=list)


@dataclass
class AccessSnapshot:
    sha256: str
    size: int
    format: str
    reader_version: str
    tables: dict[str, AccessTable]
    diagnostics: list[dict]


def normalized_name(value):
    if not isinstance(value, str) or not value or len(value) > 255 or any(ord(c) < 32 for c in value):
        raise AccessReadError("INVALID_SOURCE_NAME")
    return unicodedata.normalize("NFC", value).casefold()


def _decode(line: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AccessReadError("DUPLICATE_SOURCE_KEY")
            result[key] = value
        return result

    def nonfinite(_):
        raise AccessReadError("INVALID_SOURCE_NUMBER")

    try:
        obj = json.loads(line.decode("utf-8"), parse_float=Decimal,
                         parse_constant=nonfinite, object_pairs_hook=pairs)
        if not isinstance(obj, dict):
            raise AccessReadError("READER_PROTOCOL_ERROR")
        return obj
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, AccessReadError):
            raise
        raise AccessReadError("READER_PROTOCOL_ERROR") from None


def _run(command: list[str], consume: Callable[[bytes], None], limits: ReaderLimits,
         cancelled: threading.Event, deadline: float):
    """Drain both pipes without unbounded communicate(), and reap on every exit path."""
    env = {"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, env=env, start_new_session=True)
    except OSError:
        raise AccessReadError("READER_UNAVAILABLE") from None
    total, stderr_bytes, pending = 0, 0, bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "out")
            selector.register(process.stderr, selectors.EVENT_READ, "err")
            while selector.get_map():
                if cancelled.is_set():
                    raise AccessReadError("IMPORT_CANCELLED")
                if time.monotonic() >= deadline:
                    raise AccessReadError("READER_TIMEOUT")
                for key, _ in selector.select(timeout=min(0.05, max(0, deadline - time.monotonic()))):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == "err":
                        stderr_bytes += len(chunk)
                        if stderr_bytes > 65536:
                            raise AccessReadError("READER_OUTPUT_LIMIT")
                        continue
                    total += len(chunk)
                    if total > limits.output_bytes:
                        raise AccessReadError("READER_OUTPUT_LIMIT")
                    pending.extend(chunk)
                    while b"\n" in pending:
                        line, _, remaining = pending.partition(b"\n")
                        pending = bytearray(remaining)
                        if len(line) > limits.line_bytes:
                            raise AccessReadError("READER_OUTPUT_LIMIT")
                        consume(bytes(line))
                    if len(pending) > limits.line_bytes:
                        raise AccessReadError("READER_OUTPUT_LIMIT")
            if pending:
                raise AccessReadError("READER_PROTOCOL_ERROR")
            try:
                code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                raise AccessReadError("READER_TIMEOUT") from None
            if code or stderr_bytes:
                raise AccessReadError("ACCESS_READ_FAILED")
    finally:
        # Kill the group even if its parent exited while a descendant held a pipe.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        process.stdout.close()
        process.stderr.close()


class _Protocol:
    def __init__(self, limits):
        self.limits, self.header, self.complete = limits, None, False
        self.tables, self.diagnostics, self.closed = {}, [], set()
        self.seen_tables = set()
        self.count = 0

    def accept(self, line):
        event = _decode(line)
        kind = event.get("kind")
        if self.complete:
            raise AccessReadError("READER_PROTOCOL_ERROR")
        if kind == "error":
            raise AccessReadError(event["code"] if event.get("code") in {"ROW_LIMIT", "ACCESS_READ_FAILED"} else "ACCESS_READ_FAILED")
        if self.header is None:
            if kind != "database" or type(event.get("protocol")) is not int or event["protocol"] != 1 or event.get("readerVersion") != READER_VERSION:
                raise AccessReadError("READER_PROTOCOL_ERROR")
            if event.get("format") not in VERIFIED_FORMATS:
                raise AccessReadError("UNSUPPORTED_ACCESS_FORMAT")
            self.header = event
            return
        if kind == "diagnostic":
            if event.get("code") != "LINKED_TABLE_UNAVAILABLE" or normalized_name(event.get("table")) not in TABLES:
                raise AccessReadError("READER_PROTOCOL_ERROR")
            canonical = normalized_name(event["table"])
            if canonical in self.seen_tables:
                raise AccessReadError("AMBIGUOUS_SOURCE_SCHEMA")
            self.seen_tables.add(canonical)
            self.diagnostics.append({"code": event["code"], "table": event["table"]})
        elif kind == "table":
            name = event.get("name")
            canonical = normalized_name(name)
            if canonical not in TABLES or canonical in self.seen_tables:
                raise AccessReadError("AMBIGUOUS_SOURCE_SCHEMA")
            self.seen_tables.add(canonical)
            columns, pk = event.get("columns"), event.get("primaryKey")
            if not isinstance(columns, list) or not 1 <= len(columns) <= 256 or not isinstance(pk, list):
                raise AccessReadError("READER_PROTOCOL_ERROR")
            names = set()
            for column in columns:
                if not isinstance(column, dict) or not isinstance(column.get("type"), str) or type(column.get("readable")) is not bool:
                    raise AccessReadError("READER_PROTOCOL_ERROR")
                key = normalized_name(column.get("name"))
                if key in names:
                    raise AccessReadError("AMBIGUOUS_SOURCE_SCHEMA")
                names.add(key)
                if not column["readable"]:
                    self.diagnostics.append({"code": "UNSUPPORTED_COLUMN_TYPE", "table": name, "column": column["name"]})
            if not all(isinstance(n, str) for n in pk) or len(pk) != len(set(pk)) or not all(n in {c["name"] for c in columns} for n in pk):
                raise AccessReadError("READER_PROTOCOL_ERROR")
            self.tables[canonical] = AccessTable(name, columns, pk)
        elif kind in {"row", "tableEnd"}:
            name = normalized_name(event.get("table"))
            table = self.tables.get(name)
            if not table or name in self.closed or table.name != event["table"]:
                raise AccessReadError("READER_PROTOCOL_ERROR")
            if kind == "tableEnd":
                if type(event.get("count")) is not int or event["count"] != len(table.rows):
                    raise AccessReadError("READER_PROTOCOL_ERROR")
                self.closed.add(name)
                return
            values = event.get("values")
            if not isinstance(values, dict) or values.keys() != {c["name"] for c in table.columns if c["readable"]}:
                raise AccessReadError("READER_PROTOCOL_ERROR")
            for value in values.values():
                if value is not None and type(value) not in (str, int, Decimal, bool):
                    raise AccessReadError("READER_PROTOCOL_ERROR")
                if isinstance(value, str) and len(value) > 65536:
                    raise AccessReadError("READER_OUTPUT_LIMIT")
                if isinstance(value, Decimal) and not value.is_finite():
                    raise AccessReadError("INVALID_SOURCE_NUMBER")
            self.count += 1
            if self.count > self.limits.rows:
                raise AccessReadError("ROW_LIMIT")
            table.rows.append(values)
        elif kind == "complete":
            if type(event.get("rowCount")) is not int or event["rowCount"] != self.count or self.closed != set(self.tables):
                raise AccessReadError("READER_PROTOCOL_ERROR")
            self.complete = True
        else:
            raise AccessReadError("READER_PROTOCOL_ERROR")


class AccessReader:
    def __init__(self, jar: str | Path | None = None, *, limits: ReaderLimits | None = None,
                 temp_root: str | Path | None = None):
        self.jar = Path(jar or os.environ.get("ELS_READER_JAR", "/opt/els/reader.jar"))
        self.limits = limits or ReaderLimits()
        self.temp_root = temp_root

    def available(self):
        return self.jar.is_file() and shutil.which("java") is not None

    def read(self, source: BinaryIO, *, cancelled: threading.Event | None = None) -> AccessSnapshot:
        if not self.available():
            raise AccessReadError("READER_UNAVAILABLE")
        cancelled = cancelled or threading.Event()
        deadline = time.monotonic() + self.limits.seconds
        digest, size = hashlib.sha256(), 0
        with tempfile.TemporaryDirectory(prefix="creator-els-", dir=self.temp_root) as directory:
            path = Path(directory) / "source.access"
            with path.open("xb") as destination:
                while True:
                    if cancelled.is_set():
                        raise AccessReadError("IMPORT_CANCELLED")
                    if time.monotonic() >= deadline:
                        raise AccessReadError("READER_TIMEOUT")
                    chunk = source.read(min(65536, self.limits.file_bytes - size + 1))
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.limits.file_bytes:
                        raise AccessReadError("FILE_TOO_LARGE")
                    digest.update(chunk)
                    destination.write(chunk)
            with path.open("rb") as uploaded:
                header = uploaded.read(32)
            if size < 2048 or not (header.startswith(b"\x00\x01\x00\x00Standard Jet DB\x00") or header.startswith(b"\x00\x01\x00\x00Standard ACE DB\x00")):
                raise AccessReadError("UNSUPPORTED_ACCESS")
            path.chmod(0o400)
            protocol = _Protocol(self.limits)
            command = [shutil.which("java"), "-Xmx128m", "-XX:MaxMetaspaceSize=64m", "-XX:ActiveProcessorCount=1",
                       "-XX:+PerfDisableSharedMem", f"-Djava.io.tmpdir={directory}", "-Dfile.encoding=UTF-8",
                       "-jar", str(self.jar.resolve()), str(path), str(self.limits.rows)]
            _run(command, protocol.accept, self.limits, cancelled, deadline)
            if not protocol.complete:
                raise AccessReadError("READER_PROTOCOL_ERROR")
            return AccessSnapshot(digest.hexdigest(), size, protocol.header["format"], READER_VERSION,
                                  protocol.tables, protocol.diagnostics)
