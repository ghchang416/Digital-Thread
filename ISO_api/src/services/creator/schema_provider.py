"""Trusted schema registration. Uploaded Python modules are never executed."""
import dataclasses
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal, get_args, get_origin, get_type_hints

from pydantic import BaseModel, ConfigDict
from src.entities import model_v31

# New schema versions require an explicit, reviewed registration and profile.
REGISTERED_MODELS = {"v31": model_v31}
ACTIVE_SCHEMA = "v31"


class ReferencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    sourceType: str
    fieldName: str
    label: str
    targetRole: Literal["project", "machine", "material", "file", "tool"]
    targetType: str
    editor: Literal["asset-picker", "nc-tools"]
    key: str
    valueFormat: Literal["element-fullpath"]
    elementIdPrefix: str
    displayName: str


class SchemaProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schemaVersion: str
    assetType: str
    namespace: str
    assetTypes: dict[str, str]
    referenceType: str
    keyValueType: str
    referencePolicies: list[ReferencePolicy]


def get_model():
    return REGISTERED_MODELS[ACTIVE_SCHEMA]


def validate_profile(profile, model):
    def fields(name):
        cls = getattr(model, name, None)
        if not dataclasses.is_dataclass(cls):
            raise ValueError(f"Unknown schema type: {name}")
        return {item.name: item for item in dataclasses.fields(cls)}

    fields(profile.assetType)
    fields(profile.referenceType)
    fields(profile.keyValueType)
    for name in profile.assetTypes.values():
        fields(name)
    key_hint = get_type_hints(getattr(model, profile.keyValueType))["key"]
    key_enum = next(t for t in get_args(key_hint) if t is not type(None))
    ids, slots = set(), set()
    for policy in profile.referencePolicies:
        slot = (policy.sourceType, policy.fieldName)
        if policy.id in ids or slot in slots:
            raise ValueError("Duplicate reference policy")
        ids.add(policy.id)
        slots.add(slot)
        if policy.targetType != profile.assetTypes.get(policy.targetRole):
            raise ValueError("Reference target role/type mismatch")
        field = fields(policy.sourceType).get(policy.fieldName)
        hint = get_type_hints(getattr(model, policy.sourceType)).get(policy.fieldName)
        if field is None or get_origin(hint) is list or getattr(model, profile.referenceType) not in get_args(hint):
            raise ValueError(f"Reference field does not match schema: {slot}")
        key_enum(policy.key)
    return profile


@lru_cache(maxsize=1)
def get_profile():
    path = Path(__file__).parent / "profiles" / f"{ACTIVE_SCHEMA}.json"
    profile = SchemaProfile.model_validate_json(path.read_text(encoding="utf-8"))
    if profile.schemaVersion != ACTIVE_SCHEMA:
        raise ValueError("Schema profile version mismatch")
    return validate_profile(profile, get_model())


def policy_hash():
    value = json.dumps(get_profile().model_dump(), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(value.encode()).hexdigest()


def policy_for(type_id, field_name):
    model = get_model()
    cls = getattr(model, type_id, None)
    matches = [p for p in get_profile().referencePolicies
               if p.fieldName == field_name and isinstance(cls, type)
               and issubclass(cls, getattr(model, p.sourceType))]
    if len(matches) > 1:
        raise ValueError("Overlapping reference policies")
    return matches[0] if matches else None
