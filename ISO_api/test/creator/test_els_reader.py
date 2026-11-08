"""Reader protocol tests always run; actual Access tests require the isolated reader image."""
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import time

import pytest

from src.services.creator.els.reader import AccessReader, AccessReadError, ReaderLimits, _Protocol, _decode, _run


def test_decoder_preserves_exact_numeric_and_null_values():
    row = _decode(b'{"empty":"","null":null,"false":false,"zero":0,"number":123456789012345678.123456}')
    assert row == {"empty": "", "null": None, "false": False, "zero": 0, "number": Decimal("123456789012345678.123456")}
    assert type(row["false"]) is bool and type(row["zero"]) is int


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"v":NaN}', b'[]', b'not json', b'\xff'])
def test_bad_protocol_is_rejected(raw):
    with pytest.raises(AccessReadError):
        _decode(raw)


def test_missing_runtime_does_not_run_a_process(tmp_path):
    reader = AccessReader(tmp_path / "missing.jar")
    assert not reader.available()
    with pytest.raises(AccessReadError, match="READER_UNAVAILABLE"):
        reader.read(io.BytesIO(b""))


def test_protocol_requires_version_table_closure_and_row_counts():
    p = _Protocol(ReaderLimits())
    with pytest.raises(AccessReadError):
        p.accept(b'{"kind":"complete","rowCount":0}')
    p.accept(b'{"kind":"database","protocol":1,"readerVersion":"jackcess-4.0.8/els-1","format":"V2000"}')
    p.accept(b'{"kind":"table","name":"Part_Info","columns":[{"name":"Part_No","type":"TEXT","readable":true}],"primaryKey":["Part_No"]}')
    with pytest.raises(AccessReadError):
        p.accept(b'{"kind":"complete","rowCount":0}')
    p.accept(b'{"kind":"row","table":"Part_Info","values":{"Part_No":"001"}}')
    p.accept(b'{"kind":"tableEnd","table":"Part_Info","count":1}')
    p.accept(b'{"kind":"complete","rowCount":1}')
    assert p.complete
    with pytest.raises(AccessReadError):
        p.accept(b'{"kind":"complete","rowCount":1}')


def test_linked_diagnostic_does_not_conflict_with_unsupported_columns():
    p = _Protocol(ReaderLimits())
    p.accept(b'{"kind":"database","protocol":1,"readerVersion":"jackcess-4.0.8/els-1","format":"V2000"}')
    columns = [{"name": f"binary_{i}", "type": "OLE", "readable": False} for i in range(9)]
    p.accept(json.dumps({"kind": "table", "name": "Part_Info", "columns": columns, "primaryKey": []}).encode())
    p.accept(b'{"kind":"tableEnd","table":"Part_Info","count":0}')
    event = b'{"kind":"diagnostic","table":"Operation_Machining","code":"LINKED_TABLE_UNAVAILABLE"}'
    p.accept(event)
    assert len(p.diagnostics) == 10
    with pytest.raises(AccessReadError, match="AMBIGUOUS_SOURCE_SCHEMA"):
        p.accept(event)


def test_malformed_primary_key_is_a_sanitized_protocol_error():
    p = _Protocol(ReaderLimits())
    p.accept(b'{"kind":"database","protocol":1,"readerVersion":"jackcess-4.0.8/els-1","format":"V2000"}')
    with pytest.raises(AccessReadError, match="READER_PROTOCOL_ERROR"):
        p.accept(b'{"kind":"table","name":"Part_Info","columns":[{"name":"id","type":"TEXT","readable":true}],"primaryKey":[[]]}')


@pytest.mark.parametrize("script,code,limits", [
    ("import time; time.sleep(5)", "READER_TIMEOUT", ReaderLimits(seconds=.15)),
    ("print('x'*2000)", "READER_OUTPUT_LIMIT", ReaderLimits(line_bytes=100)),
    ("print('x'*2000)", "READER_OUTPUT_LIMIT", ReaderLimits(output_bytes=100)),
    ("import sys; sys.stderr.write('private connection string'); sys.exit(1)", "ACCESS_READ_FAILED", ReaderLimits()),
    ("import sys; sys.stdout.write('truncated')", "READER_PROTOCOL_ERROR", ReaderLimits()),
])
def test_process_limits_and_errors_are_sanitized(script, code, limits):
    with pytest.raises(AccessReadError) as exc:
        _run([sys.executable, "-c", script], lambda _: None, limits, threading.Event(), time.monotonic() + limits.seconds)
    assert str(exc.value) == code


def test_process_cancellation_reaps_child():
    cancelled = threading.Event()
    timer = threading.Timer(.1, cancelled.set)
    timer.start()
    try:
        with pytest.raises(AccessReadError, match="IMPORT_CANCELLED"):
            _run([sys.executable, "-c", "import time; time.sleep(10)"], lambda _: None,
                 ReaderLimits(), cancelled, time.monotonic() + 10)
    finally:
        timer.cancel()


@pytest.fixture
def runtime(tmp_path):
    reader = AccessReader(temp_root=tmp_path)
    if not reader.available():
        if os.environ.get("ELS_REQUIRE_RUNTIME") == "1":
            pytest.fail("Reader runtime is required in the integration job")
        pytest.skip("Run Dockerfile.els-reader-test for actual MDB/ACCDB integration")
    return reader


def fixture_path(name):
    if os.environ.get("ELS_FIXTURE_ROOT"):
        return Path(os.environ["ELS_FIXTURE_ROOT"]) / name
    local = Path(__file__).parent / "fixtures" / "els" / name
    return local if local.is_file() else Path("/fixtures") / name


def test_checked_in_fixture_checksums():
    root = Path(__file__).parent / "fixtures" / "els"
    if not root.exists():
        # The test image generates fresh semantic fixtures (Access timestamps differ).
        return
    for name, expected in json.loads((root / "checksums.json").read_text()).items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize("name,format", [("synthetic.mdb", "V2000"), ("synthetic.accdb", "V2010")])
def test_actual_access_preserves_schema_rows_and_original(runtime, name, format, tmp_path):
    path = fixture_path(name)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open("rb") as source:
        snapshot = runtime.read(source)
    assert snapshot.sha256 == before == hashlib.sha256(path.read_bytes()).hexdigest()
    assert snapshot.format == format
    assert set(snapshot.tables) == {"part_info", "operation_info", "operation_machining", "machine_milling", "tool_milling", "part_file"}
    assert snapshot.tables["part_info"].primary_key == ["Part_No", "Part_Rev"]
    rows = snapshot.tables["part_info"].rows
    assert rows[0]["Spec_재질"] is None
    assert rows[1]["Spec_재질"] == ""
    assert rows[0]["Part_Name"] == "합성 부품"
    assert snapshot.tables["operation_info"].rows[0]["Op_No"] == "010"
    steps = snapshot.tables["operation_machining"].rows
    assert steps[0]["TOOLNO"] == "001"
    assert steps[0]["SPINDLE_02"] is None
    assert steps[1]["SPINDLE_01"] == 0 and steps[1]["SPINDLE_02"] == -1000
    assert steps[0]["TEST_BOOLEAN"] is False and steps[1]["TEST_BOOLEAN"] is True
    assert steps[0]["TEST_DECIMAL"] == Decimal("123456789012345678.123456")
    assert steps[3]["DESC"] == "가공"
    assert snapshot.tables["tool_milling"].rows == []
    assert not list(tmp_path.iterdir())


def test_linked_table_is_diagnosed_without_opening_external_database(runtime):
    with fixture_path("linked.accdb").open("rb") as source:
        result = runtime.read(source)
    assert result.tables == {}
    assert result.diagnostics == [{"code": "LINKED_TABLE_UNAVAILABLE", "table": "Operation_Machining"}]


def test_invalid_file_rejected_and_temporary_file_removed(runtime, tmp_path):
    with pytest.raises(AccessReadError, match="UNSUPPORTED_ACCESS"):
        runtime.read(io.BytesIO(b'{"not":"Access"}'))
    assert not list(tmp_path.iterdir())


def test_file_size_limit_and_row_limit(runtime, tmp_path):
    data = fixture_path("synthetic.accdb").read_bytes()
    small = AccessReader(runtime.jar, limits=ReaderLimits(file_bytes=10), temp_root=tmp_path)
    with pytest.raises(AccessReadError, match="FILE_TOO_LARGE"):
        small.read(io.BytesIO(data))
    small = AccessReader(runtime.jar, limits=ReaderLimits(rows=1), temp_root=tmp_path)
    with pytest.raises(AccessReadError, match="ROW_LIMIT"):
        small.read(io.BytesIO(data))
    assert not list(tmp_path.iterdir())


def test_cancelled_input_does_not_leave_temp_files(runtime, tmp_path):
    event = threading.Event()
    event.set()
    with pytest.raises(AccessReadError, match="IMPORT_CANCELLED"):
        runtime.read(io.BytesIO(fixture_path("synthetic.mdb").read_bytes()), cancelled=event)
    assert not list(tmp_path.iterdir())


def test_unverified_access_version_is_explicitly_rejected(runtime, tmp_path):
    with fixture_path("unsupported.accdb").open("rb") as source:
        with pytest.raises(AccessReadError, match="UNSUPPORTED_ACCESS_FORMAT"):
            runtime.read(source)
    assert not list(tmp_path.iterdir())


def test_corrupt_access_has_sanitized_error_and_is_cleaned_up(runtime, tmp_path):
    data = b"\x00\x01\x00\x00Standard ACE DB\x00" + bytes(8192)
    with pytest.raises(AccessReadError, match="ACCESS_READ_FAILED"):
        runtime.read(io.BytesIO(data))
    assert not list(tmp_path.iterdir())


def test_real_access_catalog_preserves_part_and_program_boundaries(runtime):
    from src.services.creator.els.source_catalog import SourceCatalog

    with fixture_path("synthetic.accdb").open("rb") as source:
        catalog = SourceCatalog(runtime.read(source))
    assert catalog.page()["total"] == 4
    assert catalog.diagnostics == []
    item = next(op for op in catalog.page()["items"] if op["partNo"] == "P-001" and op["partRevision"] == "01" and op["opNo"] == "010")
    detail = catalog.detail(item["operationKey"])
    assert [(p["pgmNo"], p["revision"]) for p in detail["programs"]] == [("100", "A"), ("200", "B")]
    assert detail["programs"][0]["rows"][0]["values"]["TEST_DECIMAL"] == "123456789012345678.123456"
