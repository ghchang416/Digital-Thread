"""Copy a bounded OP/program context out of an owned reader session."""
import hashlib
import json

from .profile import load_profile
from .reader import normalized_name
from .source_catalog import opaque, public_value


def cells(values):
    return {normalized_name(k): (k, v) for k, v in values.items()}


def value(row, column):
    return cells(row["values"]).get(normalized_name(column), (None, None))[1]


def source_context(catalog, operation_key, program_key):
    detail = catalog.details.get(operation_key)
    if not detail:
        raise ValueError("ELS_OPERATION_NOT_FOUND")
    programs = [p for p in detail["programs"] if p["programKey"] == program_key]
    if len(programs) != 1 or not programs[0]["selectable"]:
        raise ValueError("ELS_PROGRAM_NOT_FOUND")
    program = programs[0]
    if len(program["rows"]) > 900:
        raise ValueError("ELS_SOURCE_SELECTION_LIMIT")
    if any(i["code"] in {"DUPLICATE_SOURCE_KEY", "PART_REFERENCE_INVALID"} for i in detail["issues"]):
        raise ValueError("ELS_AMBIGUOUS_OPERATION")
    profile, _ = load_profile()
    snapshot = catalog.snapshot
    columns = set(profile.toolIdentityColumns + profile.preserveOnlyColumns)
    columns.update(c for rule in profile.numericRules for c in rule.columns)
    columns.update(["Part_No", "Part_Rev", "Op_No", "PGMNO", "REVNO", "SEQNO", "TOOLNO", "Operation_Machining_SN", "DESC"])

    def keep(row, names):
        wanted = {normalized_name(n) for n in names}
        return {k: public_value(v) for k, v in row.items() if normalized_name(k) in wanted}

    def related(table_name, keys, names):
        table = snapshot.tables.get(table_name.lower())
        if not table:
            return []
        found = []
        for ordinal, row in enumerate(table.rows):
            normalized = {normalized_name(k): v for k, v in row.items()}
            if all(normalized.get(normalized_name(k)) == v for k, v in keys.items()):
                found.append(dict(rowId=opaque("source", snapshot.sha256, table_name, ordinal), table=table_name,
                                  values=keep(row, names)))
                if len(found) > 100:
                    raise ValueError("ELS_RELATED_ROWS_LIMIT")
        return found

    part_keys = {"Part_No": detail["partNo"], "Part_Rev": detail["partRevision"]}
    parts = related("Part_Info", part_keys, [*part_keys, "Part_Name", "Part_Material", "Spec_재질"])
    ops = related("Operation_Info", {**part_keys, "Op_No": detail["opNo"]},
                  [*part_keys, "Op_No", "공정 Type", "설비코드", "설비번호"])
    if len(parts) != 1 or len(ops) != 1:
        raise ValueError("ELS_AMBIGUOUS_OPERATION")
    machine_keys = {"설비코드": detail["machineCode"], "설비번호": detail["machineNumber"]}
    machines = related("Machine_Milling", machine_keys, [*machine_keys, "설비명"]) if all(
        isinstance(v, str) and v.strip() for v in machine_keys.values()) else []
    rows = [{**r, "values": keep(r["values"], columns)} for r in program["rows"]]
    schema = {n: {"columns": t.columns, "primaryKey": t.primary_key} for n, t in snapshot.tables.items()}
    result = dict(sourceSha256=snapshot.sha256, readerVersion=snapshot.reader_version,
                  sourceSchemaHash=hashlib.sha256(json.dumps(schema, sort_keys=True, ensure_ascii=True).encode()).hexdigest(),
                  part=parts[0], operation=ops[0], machines=machines,
                  files=related("Part_File", part_keys, [*part_keys, "File_Path"]),
                  rows=rows, programNo=program["pgmNo"], programRevision=program["revision"])
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode()) > 1024 * 1024:
        raise ValueError("ELS_SOURCE_SELECTION_BUDGET")
    return json.loads(encoded)
