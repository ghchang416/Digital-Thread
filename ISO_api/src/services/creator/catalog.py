"""Extract XML field metadata without importing the model through user input."""

import dataclasses
import hashlib
import inspect
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import get_args, get_origin, get_type_hints

from src.services.creator.schema_provider import get_model, get_profile, policy_for, policy_hash
RULES_VERSION = "creator-cam-1"

LABELS = {
    "DtFile": "파일", "DtCuttingTool13399": "13399 절삭 공구", "NumericalValue": "공구 수치",
    "DtProject": "프로젝트", "DtMachineTool": "머신 툴", "DtMaterial": "마테리얼",
    "MachineToolRequirements": "장비 요구사항", "MachineToolSpecification": "장비 사양",
    "Workplan": "워크플랜", "Workpiece": "워크피스", "MachiningWorkingstep": "워킹스텝",
    "NumericParameter": "수치 물성", "DescriptiveParameter": "설명형 물성",
    "PropertyParameter": "물성 항목", "SpindleCapability": "주축 능력",
}
FIELD_LABELS = {
    "numerical_value": "공구 수치", "value_name": "수치 항목", "value_component": "수치 값",
    "element_id": "요소 ID", "display_name": "표시 이름", "element_description": "설명",
    "category": "분류", "its_id": "식별자", "main_workplan": "메인 워크플랜",
    "its_elements": "실행 요소", "its_workpieces": "워크피스", "description": "설명",
    "machine_tool": "머신 타입", "standard_identifier": "재료 표준 식별자",
    "material_identifier": "재료 식별자", "material_property": "재료 물성",
    "parameter_name": "물성 이름", "its_parameter_value": "물성 값",
    "its_parameter_unit": "단위", "descriptive_string": "물성 설명",
    "automatically_pallet_changeable": "자동 팔레트 교환", "spindles": "주축",
    "number_of_tools_in_tool_magazine": "공구 매거진 수용 수", "axis": "축 구성",
    "its_secplane": "안전 평면", "its_feature": "가공 피처", "its_operation": "가공 작업",
    "its_technology": "가공 기술", "its_machine_functions": "기계 기능", "its_tool": "가공 공구",
    "its_machining_strategy": "가공 전략", "feedrate": "이송 속도", "spindle": "주축 속도",
    "effective_cutting_diameter": "유효 절삭 지름", "edge_radius": "날끝 반경",
    "overall_assembly_length": "전체 조립 길이", "number_of_effective_teeth": "유효 날 수",
    "its_cutting_edges": "절삭날", "tool_functional_length": "공구 기능 길이",
    "its_milling_tolerances": "밀링 공차", "chordal_tolerance": "현 공차", "scallop_height": "스캘럽 높이",
    "cutmode": "절삭 방향", "pathmode": "경로 방향", "coolant": "절삭유", "stepover": "스텝오버",
    "axial_cutting_depth": "축 방향 절삭 깊이", "radial_cutting_depth": "반경 방향 절삭 깊이",
    "allowance_side": "측면 가공 여유", "through_spindle_coolant": "주축 관통 절삭유",
    "chip_removal": "칩 제거", "feedrate_reference": "이송 속도 기준",
}


@lru_cache(maxsize=1)
def model_classes():
    model = get_model()
    return {
        name: cls for name, cls in vars(model).items()
        if isinstance(cls, type) and cls.__module__ == model.__name__ and dataclasses.is_dataclass(cls)
    }


def _atoms(hint):
    args = get_args(hint)
    return [part for arg in args for part in _atoms(arg)] if args else ([] if hint is type(None) else [hint])


@lru_cache(maxsize=1)
def get_catalog():
    model, profile = get_model(), get_profile()
    classes = model_classes()
    enums = {
        name: [item.value for item in cls]
        for name, cls in vars(model).items()
        if isinstance(cls, type) and cls.__module__ == model.__name__ and issubclass(cls, Enum)
    }
    types = {}
    for name, cls in classes.items():
        hints = get_type_hints(cls, vars(model))
        fields = []
        for item in dataclasses.fields(cls):
            atoms = _atoms(hints[item.name])
            objects = [t.__name__ for t in atoms if t.__name__ in classes]
            enum_ids = [t.__name__ for t in atoms if t.__name__ in enums]
            scalar_types = [t.__name__ for t in atoms if t in (str, int, float, bool)]
            owner = next(base.__name__ for base in cls.__mro__ if item.name in base.__dict__.get("__annotations__", {}))
            repeated = get_origin(hints[item.name]) is list
            meta = dict(item.metadata)
            minimum = meta.get("min_occurs", 1 if meta.get("required") else 0)
            policy = policy_for(name, item.name)
            fields.append({
                "fieldName": item.name, "label": policy.label if policy else FIELD_LABELS.get(item.name, item.name),
                "declaredBy": owner, "xmlName": meta.get("name", item.name),
                "xmlKind": meta.get("type", "Element"), "namespace": meta.get("namespace"),
                "kind": "object" if objects else "enum" if enum_ids else "scalar",
                "objectTypes": objects, "enumTypes": enum_ids, "scalarTypes": scalar_types,
                "repeated": repeated, "minOccurs": minimum,
                "maxOccurs": meta.get("max_occurs", None if repeated else 1),
                "required": minimum > 0, "managed": policy is not None,
                "referencePolicyId": policy.id if policy else None,
                "metadata": meta,
            })
        types[name] = {
            "typeId": name, "label": LABELS.get(name, name),
            "xmlName": getattr(getattr(cls, "Meta", None), "name", name),
            "bases": [base.__name__ for base in cls.__bases__ if base.__name__ in classes],
            "descendants": [other for other, candidate in classes.items() if other != name and issubclass(candidate, cls)],
            "fields": fields, "semanticStatus": "not-reviewed",
        }
    return {
        "catalogVersion": 1, "schemaVersion": profile.schemaVersion, "rulesVersion": RULES_VERSION,
        "schemaHash": hashlib.sha256(Path(inspect.getfile(model)).read_bytes()).hexdigest(),
        "types": types, "enums": enums, "rootTypes": list(profile.assetTypes.values()),
        "referencePolicies": [p.model_dump() for p in profile.referencePolicies],
        "referencePolicyHash": policy_hash(),
        "capabilities": {"partialPreview": True, "finalReview": False, "finalSave": False, "camParse": True},
        "limits": {"maxNodes": 10000, "maxDepth": 64, "maxRequestBytes": 2 * 1024 * 1024,
                   "maxCamFileBytes": 8 * 1024 * 1024, "maxCamRequestBytes": 32 * 1024 * 1024,
                   "maxCamFiles": 50, "maxCamOperations": 300},
        "validationScope": "model-metadata-only",
    }
