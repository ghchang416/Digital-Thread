"""PART/REV/OP inspection only. This layer never chooses machining/tool defaults."""
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import re

from .reader import AccessSnapshot, normalized_name


REQUIRED = {
    "part_info": ("Part_No", "Part_Rev"),
    "operation_info": ("Part_No", "Part_Rev", "Op_No"),
    "operation_machining": ("Part_No", "Part_Rev", "Op_No", "PGMNO", "REVNO", "SEQNO", "TOOLNO"),
}


def public_value(value):
    # Keep exact decimals/large integers as text across the JSON/JavaScript boundary.
    if isinstance(value, Decimal) or (type(value) is int and abs(value) > 9007199254740991):
        return str(value)
    if isinstance(value, dict):
        return {key: public_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [public_value(item) for item in value]
    return value


def opaque(kind, *values):
    encoded = json.dumps(public_value(values), ensure_ascii=True, separators=(",", ":"))
    return kind + "_" + hashlib.sha256(encoded.encode()).hexdigest()[:32]


def text_key(row, fields):
    values = tuple(row.get(normalized_name(field)) for field in fields)
    return values if all(isinstance(value, str) and value.strip() for value in values) else None


def natural_key(value):
    # Length/lexical ordering avoids constructing an unbounded integer from an identifier.
    return tuple((1, len(part.lstrip("0")), part.lstrip("0")) if part.isascii() and part.isdecimal()
                 else (0, part.casefold()) for part in re.split(r"([0-9]+)", value))


class SourceCatalog:
    def __init__(self, snapshot: AccessSnapshot):
        self.snapshot = snapshot
        self.diagnostics = [dict(item) for item in snapshot.diagnostics]
        self.rows = {}
        for name, table in snapshot.tables.items():
            columns = {normalized_name(column["name"]) for column in table.columns if column["readable"]}
            for field in REQUIRED.get(name, ()):
                if normalized_name(field) not in columns:
                    self.diagnostics.append({"code": "MISSING_COLUMN", "table": table.name, "column": field})
            self.rows[name] = [{normalized_name(k): v for k, v in row.items()} for row in table.rows]
        for name in REQUIRED.keys() - snapshot.tables.keys():
            self.diagnostics.append({"code": "MISSING_TABLE", "table": name})
        self.operations, self.details = [], {}
        self._index()

    def _index(self):
        parts, machining, operations = defaultdict(list), defaultdict(list), defaultdict(list)
        for table_name, fields, index in [
            ("part_info", REQUIRED["part_info"], parts),
            ("operation_info", REQUIRED["operation_info"], operations),
            ("operation_machining", REQUIRED["operation_info"], machining),
        ]:
            for ordinal, row in enumerate(self.rows.get(table_name, [])):
                key = text_key(row, fields)
                if key is None:
                    self.diagnostics.append({"code": "INVALID_SOURCE_KEY", "table": table_name, "sourceRow": ordinal})
                    continue
                index[key].append((ordinal, row))
        for key, values in parts.items():
            if len(values) > 1:
                self.diagnostics.append({"code": "DUPLICATE_SOURCE_KEY", "table": "part_info", "key": list(key)})
        sn_counts = Counter(str(row["operation_machining_sn"]) for row in self.rows.get("operation_machining", [])
                            if row.get("operation_machining_sn") is not None)
        for key, op_rows in operations.items():
            cached_programs, cached_issues = None, None
            for ordinal, op in op_rows:
                issues, programs = [], defaultdict(list)
                if len(op_rows) > 1:
                    issues.append({"code": "DUPLICATE_SOURCE_KEY", "table": "operation_info"})
                parent = parts.get(key[:2], [])
                if len(parent) != 1:
                    issues.append({"code": "PART_REFERENCE_INVALID", "table": "part_info"})
                operation_key = opaque("op", self.snapshot.sha256, key, ordinal)
                for position, row in machining.get(key, []) if cached_programs is None else []:
                    program = text_key(row, ("PGMNO", "REVNO"))
                    if program is None:
                        issues.append({"code": "PROGRAM_SELECTION_REQUIRED", "sourceRow": position})
                    sn = row.get("operation_machining_sn")
                    row_issues = []
                    if sn is None or type(sn) is bool or (isinstance(sn, str) and not sn.strip()):
                        row_issues.append({"code": "SOURCE_ROW_KEY_MISSING"})
                    elif sn_counts[str(sn)] > 1:
                        row_issues.append({"code": "DUPLICATE_SOURCE_KEY", "column": "Operation_Machining_SN"})
                    seq = row.get("seqno")
                    if type(seq) not in (int, Decimal) or (isinstance(seq, Decimal) and not seq.is_finite()):
                        row_issues.append({"code": "INVALID_SEQUENCE"})
                    original = self.snapshot.tables["operation_machining"].rows[position]
                    programs[program].append({"rowId": opaque("row", self.snapshot.sha256, position),
                                              "sourceRow": position, "sourceSN": public_value(sn),
                                              "values": public_value(original), "issues": row_issues,
                                              "_seq": seq})
                result_programs = []
                for program, rows in programs.items():
                    seq_counts = Counter(row["_seq"] for row in rows if type(row["_seq"]) in (int, Decimal))
                    for row in rows:
                        if type(row["_seq"]) in (int, Decimal) and seq_counts[row["_seq"]] > 1:
                            row["issues"].append({"code": "SEQ_CONFLICT", "column": "SEQNO"})
                    rows.sort(key=lambda row: (type(row["_seq"]) not in (int, Decimal),
                                              row["_seq"] if type(row["_seq"]) in (int, Decimal) else 0,
                                              row["sourceRow"]))
                    for row in rows:
                        del row["_seq"]
                    result_programs.append({"programKey": opaque("program", operation_key, program),
                                            "pgmNo": program[0] if program else None,
                                            "revision": program[1] if program else None, "rows": rows,
                                            "selectable": program is not None})
                # Ambiguous duplicate OP records remain visible but share one read-only row index.
                if cached_programs is None:
                    cached_programs = result_programs
                    cached_issues = [issue for issue in issues if issue["code"] == "PROGRAM_SELECTION_REQUIRED"]
                    row_count = sum(len(p["rows"]) for p in result_programs)
                    row_issue_count = sum(len(row["issues"]) for p in result_programs for row in p["rows"])
                else:
                    result_programs = cached_programs
                    issues.extend(cached_issues)
                if not result_programs:
                    issues.append({"code": "NO_MACHINING_ROWS"})
                part = parent[0][1] if len(parent) == 1 else {}
                summary = public_value({"operationKey": operation_key, "partNo": key[0], "partRevision": key[1], "opNo": key[2],
                           "partName": part.get("part_name"), "sourceType": op.get(normalized_name("공정 Type")),
                           "machineCode": op.get("설비코드"), "machineNumber": op.get("설비번호"),
                           "rowCount": row_count, "programCount": len(result_programs),
                           "issueCount": len(issues) + row_issue_count})
                self.operations.append(summary)
                self.details[operation_key] = {**summary, "issues": issues, "programs": result_programs}
        for key in machining.keys() - operations.keys():
            self.diagnostics.append({"code": "ORPHAN_MACHINING_ROWS", "key": list(key), "count": len(machining[key])})
        self.operations.sort(key=lambda op: (natural_key(op["partNo"]), natural_key(op["partRevision"]),
                                             natural_key(op["opNo"]), op["operationKey"]))

    def page(self, *, search="", cursor=None, page_size=50):
        if not isinstance(search, str) or len(search) > 256 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError("INVALID_PAGE")
        search = search.casefold()
        selected = [op for op in self.operations if search in " ".join(str(op.get(k) or "") for k in
                    ("partNo", "partRevision", "opNo", "partName", "machineCode", "machineNumber")).casefold()]
        start = 0
        if cursor:
            matches = [i for i, op in enumerate(selected) if op["operationKey"] == cursor]
            if len(matches) != 1:
                raise ValueError("INVALID_CURSOR")
            start = matches[0] + 1
        page = selected[start:start + page_size]
        return {"items": public_value([dict(op) for op in page]), "total": len(selected),
                "nextCursor": page[-1]["operationKey"] if start + page_size < len(selected) else None}

    def detail(self, operation_key):
        if operation_key not in self.details:
            raise ValueError("OPERATION_NOT_FOUND")
        # Return a fresh value: caller decisions must not mutate the source snapshot.
        return json.loads(json.dumps(self.details[operation_key], ensure_ascii=False))
