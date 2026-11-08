from copy import deepcopy
from decimal import Decimal

import pytest

from src.services.creator.els.reader import AccessSnapshot, AccessTable
from src.services.creator.els.source_catalog import SourceCatalog, public_value


def snapshot():
    parts = [{"Part_No": "P1", "Part_Rev": rev, "Part_Name": "시험 부품"} for rev in ("01", "02")]
    operations = [{"Part_No": "P1", "Part_Rev": rev, "Op_No": op} for rev, op in (("01", "010"), ("01", "10"), ("02", "010"))]
    steps = [{"Operation_Machining_SN": sn, "Part_No": "P1", "Part_Rev": rev, "Op_No": op,
              "PGMNO": "100", "REVNO": pgmrev, "SEQNO": seq, "TOOLNO": "001"}
             for sn, rev, op, pgmrev, seq in ((1, "01", "010", "A", 20), (2, "01", "010", "A", 10),
                                            (3, "01", "010", "B", 10), (4, "02", "010", "A", 0))]
    tables = {}
    for name, rows in (("Part_Info", parts), ("Operation_Info", operations), ("Operation_Machining", steps)):
        tables[name.lower()] = AccessTable(name, [{"name": k, "type": "TEXT", "readable": True} for k in rows[0]], [], rows)
    return AccessSnapshot("a" * 64, 10, "V2000", "test", tables, [])


def test_part_revision_and_text_op_keys_remain_separate():
    source = snapshot()
    original = deepcopy(source)
    catalog = SourceCatalog(source)
    assert source == original
    assert len(catalog.operations) == 3
    op = next(op for op in catalog.operations if op["partRevision"] == "01" and op["opNo"] == "010")
    detail = catalog.detail(op["operationKey"])
    assert len(detail["programs"]) == 2
    assert [r["sourceSN"] for r in detail["programs"][0]["rows"]] == [2, 1]
    assert all(row["values"]["Part_Rev"] == "01" for pgm in detail["programs"] for row in pgm["rows"])
    detail["programs"].clear()
    assert len(catalog.detail(op["operationKey"])["programs"]) == 2


def test_empty_op_is_visible_and_tool_master_is_optional():
    catalog = SourceCatalog(snapshot())
    assert catalog.diagnostics == []
    op = next(op for op in catalog.operations if op["opNo"] == "10")
    assert op["rowCount"] == 0 and catalog.detail(op["operationKey"])["issues"][0]["code"] == "NO_MACHINING_ROWS"


def test_page_and_cursor_are_stable_and_do_not_select_latest_revision():
    catalog = SourceCatalog(snapshot())
    first = catalog.page(page_size=1)
    second = catalog.page(page_size=1, cursor=first["nextCursor"])
    assert first["items"][0]["operationKey"] != second["items"][0]["operationKey"]
    assert catalog.page(search="시험 부품")["total"] == 3
    assert catalog.page(search="missing")["items"] == []
    with pytest.raises(ValueError, match="INVALID_CURSOR"):
        catalog.page(cursor="other-source")


def test_duplicate_seq_sn_and_op_are_diagnostics_not_silent_deduplication():
    source = snapshot()
    source.tables["operation_machining"].rows[1]["SEQNO"] = 20
    source.tables["operation_machining"].rows[1]["Operation_Machining_SN"] = 1
    source.tables["operation_info"].rows.append(dict(source.tables["operation_info"].rows[0]))
    catalog = SourceCatalog(source)
    matches = [op for op in catalog.operations if op["partRevision"] == "01" and op["opNo"] == "010"]
    assert len(matches) == 2 and matches[0]["operationKey"] != matches[1]["operationKey"]
    detail = catalog.detail(matches[0]["operationKey"])
    assert detail["issues"][0]["code"] == "DUPLICATE_SOURCE_KEY"
    rows = detail["programs"][0]["rows"]
    assert rows[0]["rowId"] != rows[1]["rowId"]
    assert all({i["code"] for i in r["issues"]} == {"SEQ_CONFLICT", "DUPLICATE_SOURCE_KEY"} for r in rows)


def test_missing_schema_and_orphans_are_reported_without_losing_other_ops():
    source = snapshot()
    del source.tables["part_info"]
    source.tables["operation_machining"].rows[0]["Part_No"] = "UNKNOWN"
    catalog = SourceCatalog(source)
    assert {d["code"] for d in catalog.diagnostics} >= {"MISSING_TABLE", "ORPHAN_MACHINING_ROWS"}
    assert len(catalog.operations) == 3


def test_invalid_text_key_does_not_merge_with_leading_zero_identifier():
    source = snapshot()
    source.tables["operation_info"].rows[0]["Op_No"] = 10
    catalog = SourceCatalog(source)
    assert len(catalog.operations) == 2
    assert any(d["code"] == "INVALID_SOURCE_KEY" for d in catalog.diagnostics)


def test_exact_numbers_survive_javascript_boundary():
    assert public_value({"n": Decimal("123456789012345678.123456"), "i": 9007199254740993, "b": False, "z": 0}) == {
        "n": "123456789012345678.123456", "i": "9007199254740993", "b": False, "z": 0}


def test_duplicate_operation_does_not_duplicate_machining_storage():
    source = snapshot()
    source.tables["operation_info"].rows.extend(dict(source.tables["operation_info"].rows[0]) for _ in range(1000))
    catalog = SourceCatalog(source)
    matches = [op for op in catalog.operations if op["partRevision"] == "01" and op["opNo"] == "010"]
    indexes = [catalog.details[op["operationKey"]]["programs"] for op in matches]
    assert len(matches) == 1001
    assert all(index is indexes[0] for index in indexes)


def test_page_does_not_expose_mutable_index_and_handles_long_identifiers():
    source = snapshot()
    source.tables["operation_info"].rows[0]["Op_No"] = "1" * 5000
    catalog = SourceCatalog(source)
    result = catalog.page()
    operation_key = result["items"][0]["operationKey"]
    result["items"][0]["opNo"] = "CHANGED"
    assert catalog.detail(operation_key)["opNo"] != "CHANGED"
