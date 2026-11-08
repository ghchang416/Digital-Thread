"""Explicit ELS-only rules; existing schema/manual profile hashes are untouched."""
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from src.schemas.creator import Scalar, StrictModel
from src.schemas.creator_els import SourceKey, Table
from src.services.creator.catalog import get_catalog
from src.services.creator.cam import convert_scalar
from .reader import normalized_name


class Limits(StrictModel):
    maxSteps: int = Field(gt=0, le=300, strict=True)
    maxNodes: int = Field(gt=0, le=10000, strict=True)
    maxDepth: int = Field(gt=0, le=64, strict=True)
    maxExpansion: int = Field(gt=0, le=10000, strict=True)
    maxDraftBytes: int = Field(gt=0, le=1835008, strict=True)
    maxRequestBytes: int = Field(gt=0, le=2097152, strict=True)


class NumericRule(StrictModel):
    id: SourceKey
    table: Table
    columns: list[SourceKey] = Field(min_length=1, max_length=16)
    targetType: SourceKey
    targetField: SourceKey
    sourceUnit: SourceKey
    targetUnit: SourceKey
    divisor: SourceKey
    requiresSelection: StrictBool

    @model_validator(mode="after")
    def valid_divisor(self):
        try:
            number = Decimal(self.divisor)
            if not number.is_finite() or number <= 0:
                raise ValueError("Invalid divisor")
        except InvalidOperation:
            raise ValueError("Invalid divisor") from None
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("Duplicate candidate columns")
        return self


class DefaultRule(StrictModel):
    typeId: SourceKey
    field: SourceKey
    value: Scalar
    kind: Literal["default", "placeholder"]
    reason: SourceKey


class Coverage(StrictModel):
    types: list[SourceKey] = Field(min_length=1)
    status: Literal["verified-staged-vertical", "deferred"]
    reason: SourceKey


class ElsProfile(StrictModel):
    version: SourceKey
    schemaVersion: Literal["v31"]
    capability: Literal["els-import-v1"]
    status: Literal["staged-vertical"]
    limits: Limits
    keys: dict[str, list[SourceKey]]
    numericRules: list[NumericRule]
    defaults: list[DefaultRule]
    preserveOnlyColumns: list[SourceKey]
    toolIdentityColumns: list[SourceKey] = Field(min_length=1, max_length=64)
    coverage: list[Coverage]


def load_profile():
    path = Path(__file__).parents[1] / "profiles" / "els_milling_v1.json"
    profile = ElsProfile.model_validate_json(path.read_text(encoding="utf-8"))
    catalog = get_catalog()

    def field(type_id, name):
        info = next((f for f in catalog["types"].get(type_id, {}).get("fields", []) if f["fieldName"] == name), None)
        if not info or info["managed"] or info["repeated"] or info["kind"] == "object":
            raise ValueError("ELS profile target is not a scalar field")
        return info

    if len({rule.id for rule in profile.numericRules}) != len(profile.numericRules):
        raise ValueError("Duplicate ELS numeric rules")
    slots = [(rule.typeId, rule.field) for rule in profile.defaults]
    if len(set(slots)) != len(slots):
        raise ValueError("Duplicate ELS defaults")
    for rule in profile.numericRules:
        info = field(rule.targetType, rule.targetField)
        if not set(info["scalarTypes"]) & {"float", "int"}:
            raise ValueError("ELS numeric rule requires a numeric target")
    for rule in profile.defaults:
        convert_scalar(rule.value, field(rule.typeId, rule.field), catalog)
    for coverage in profile.coverage:
        if any(name not in catalog["types"] for name in coverage.types):
            raise ValueError("ELS coverage names an unknown type")
    raw = json.dumps(profile.model_dump(), sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return profile, hashlib.sha256(raw.encode()).hexdigest()


def numeric_candidate(rule: NumericRule, row: dict, *, column=None, reason=None):
    """Return a candidate, never mutate source values or silently resolve conflicts."""
    normalized = {normalized_name(name): value for name, value in row.items()}
    if len(normalized) != len(row):
        raise ValueError("Ambiguous source columns")
    values, invalid = {}, []
    for name in rule.columns:
        value = normalized.get(normalized_name(name))
        if value is None or value == "":
            continue
        try:
            if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
                raise ValueError()
            number = Decimal(str(value))
            if not number.is_finite() or number < 0 or number > Decimal('1e308'):
                raise ValueError()
            values[name] = number
        except (ValueError, InvalidOperation):
            invalid.append(name)
    if column is not None:
        if column not in values or not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise ValueError("Explicit candidate selection requires a valid column and reason")
        selected = [column]
    elif invalid:
        return {"status": "invalid", "columns": invalid}
    elif not values:
        return {"status": "missing", "columns": []}
    elif rule.requiresSelection or len(set(values.values())) != 1:
        return {"status": "selection-required", "columns": list(values)}
    else:
        selected = list(values)
    return {"status": "candidate", "value": str(values[selected[0]] / Decimal(rule.divisor)),
            "columns": selected, "sourceUnit": rule.sourceUnit, "targetUnit": rule.targetUnit,
            "rule": rule.id, "reason": reason, "unrepresentedColumns": [name for name in values if name not in selected] + invalid}
