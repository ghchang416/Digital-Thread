"""Explicit authoring templates, never machine-ready defaults or persistence."""
from uuid import uuid4
from pydantic import ValidationError
from src.schemas.creator import CreatorDraft
from src.services.creator.cam import CamInputError, convert_scalar
from src.services.creator.catalog import get_catalog, model_classes

VERSION = "authoring-template-1"
DEFAULTS = {
    "feedrate_reference": "tcp", "synchronize_spindle_with_feed": False,
    "inhibit_feedrate_override": False, "inhibit_spindle_override": False,
    "coolant": False, "through_spindle_coolant": False, "chip_removal": False,
    "pathmode": "forward", "cutmode": "climb",
}
NUMBERS = {"maximum_depth_of_cut", "overall_assembly_length", "effective_cutting_diameter",
           "tool_functional_length", "chordal_tolerance", "scallop_height"}
SPECIALS = {"security_plane_z", "feature_depth_z"}
SUPPORTED_BASES = {"MachiningWorkingstep", "ManufacturingFeature", "MillingMachiningOperation",
                   "MillingTechnology", "MillingMachineFunctions", "MillingMachineCuttingTool",
                   "MachiningTool", "CuttingComponent", "FreeformStrategy", "Tolerances",
                   "Plane", "Axis2Placement3D", "CartesianPoint", "Workpiece"}


def ref_id(value):
    return value.get("$node") if isinstance(value, dict) else None


def complete_workplan(request):
    catalog, classes = get_catalog(), model_classes()
    draft = request.draft.model_dump(by_alias=True)
    if draft["schemaHash"] != catalog["schemaHash"] or draft["rulesVersion"] != catalog["rulesVersion"]:
        raise CamInputError("스키마가 변경되었습니다. 다시 불러와 주세요.")
    nodes = draft["nodes"]
    wp = nodes.get(request.workplanNodeId)
    if not wp or wp["typeId"] != "Workplan":
        raise CamInputError("대상 워크플랜을 선택해 주세요.")
    if set(request.overrides) - set(DEFAULTS) - NUMBERS - SPECIALS:
        raise CamInputError("허용되지 않은 공통 보완 항목입니다.")
    # Validate every supplied override even if no current node needs it.
    for name, value in request.overrides.items():
        if name in NUMBERS | SPECIALS:
            if type(value) not in (float, int) or (name in NUMBERS and value < 0):
                raise CamInputError("공통 수치는 유한한 숫자여야 하며 치수·공차는 음수일 수 없습니다.")
        elif isinstance(DEFAULTS[name], bool):
            if type(value) is not bool:
                raise CamInputError("공통 제어값은 예/아니오를 선택해 주세요.")
        else:
            enum = {"feedrate_reference": "ToolReferencePoint", "pathmode": "PathmodeType", "cutmode": "CutmodeType"}[name]
            if value not in catalog["enums"][enum]:
                raise CamInputError("공통 선택값을 확인해 주세요.")
    elements = wp["fields"].get("its_elements", [])
    if not isinstance(elements, list):
        raise CamInputError("워크플랜 실행 요소 형식을 확인해 주세요.")
    steps = [ref_id(ref) for ref in elements if nodes.get(ref_id(ref), {}).get("typeId") == "MachiningWorkingstep"]
    if not steps or len(steps) > 300 or len(set(steps)) != len(steps):
        raise CamInputError("직접 연결된 밀링 워킹스텝 1~300개를 선택해 주세요.")
    original_ids = set(nodes)
    entries, skipped = [], []

    def is_type(node, base):
        cls = classes.get(node["typeId"])
        return cls is not None and issubclass(cls, classes[base])

    def field_info(node, name):
        return next((f for f in catalog["types"].get(node["typeId"], {}).get("fields", []) if f["fieldName"] == name), None)

    def missing(node, name):
        value = node["fields"].get(name)
        return value is None or (isinstance(value, str) and not value.strip())

    def put(node, name, value, kind, reason):
        info = field_info(node, name)
        if not info or info["managed"] or not missing(node, name):
            return False
        if info["kind"] != "object" and not info["repeated"]:
            value = convert_scalar(value, info, catalog)
        node["fields"][name] = value
        entries.append({"nodeId": node["nodeId"], "fieldName": name, "value": value,
                        "kind": kind, "rule": VERSION, "reason": reason})
        return True

    def create(type_id):
        if len(nodes) >= catalog["limits"]["maxNodes"]:
            raise CamInputError("보완 후 객체 수가 제한을 초과합니다.")
        id = str(uuid4())
        node = {"nodeId": id, "typeId": type_id, "fields": {}}
        nodes[id] = node
        return node

    def object_field(node, name, type_id, kind, reason):
        info = field_info(node, name)
        if not info or info["kind"] != "object" or info["repeated"] or not missing(node, name):
            return None
        if not any(issubclass(classes[type_id], classes[base]) for base in info["objectTypes"]):
            return None
        child = create(type_id)
        put(node, name, {"$node": child["nodeId"]}, kind, reason)
        return child

    def placement(node, name, z=None, kind="placeholder"):
        child = object_field(node, name, "Axis2Placement3D", kind, "작성용 좌표 배치. 실제 좌표계·위치는 검증되지 않았습니다.")
        if child and z is not None:
            point = object_field(child, "location", "CartesianPoint", kind, "작성용 좌표. 실제 위치 확인이 필요합니다.")
            put(point, "coordinates", [{"itemId": str(uuid4()), "value": v} for v in (0.0, 0.0, z)], kind, "X/Y=0 가정. Z는 공통 설정 또는 임시값입니다.")

    def plane(node, name, override):
        if not request.includePlaceholders:
            return
        child = object_field(node, name, "Plane", "placeholder", "작성용 임시 평면. 가공 안전성·형상은 검증되지 않았습니다.")
        if child:
            placement(child, "position", request.overrides.get(override, 0.0))
        else:
            existing = nodes.get(ref_id(node["fields"].get(name)))
            if existing and existing["nodeId"] not in shared and existing["typeId"] == "Plane":
                placement(existing, "position", request.overrides.get(override, 0.0))

    # Shared objects belonging to another workplan must not be changed by this batch.
    def reachable(roots):
        found, stack = set(), list(roots)
        while stack:
            id = stack.pop()
            if id in found or id not in nodes:
                continue
            found.add(id)
            for value in nodes[id]["fields"].values():
                stack.extend(ref_id(item) for item in (value if isinstance(value, list) else [value]) if ref_id(item))
        return found
    selected_nodes = reachable(steps)
    other_steps = [id for id, n in nodes.items() if n["typeId"] in ("MachiningWorkingstep", "TurningWorkingstep") and id not in steps]
    shared = selected_nodes & reachable(other_steps)
    other_workplans = [id for id, n in nodes.items() if n["typeId"] == "Workplan" and id != request.workplanNodeId
                      and isinstance(n["fields"].get("its_elements"), list)
                      and any(ref_id(item) in steps for item in n["fields"]["its_elements"])]
    if other_workplans:
        raise CamInputError("다른 워크플랜에도 연결된 워킹스텝은 공통 보완할 수 없습니다.")
    visited = set()

    def visit(id, depth=0):
        if id in visited or id not in nodes:
            return
        if depth >= 48:
            raise CamInputError("보완 대상 객체가 너무 깊습니다.")
        visited.add(id)
        node = nodes[id]
        if id in shared:
            skipped.append({"nodeId": id, "message": "다른 워킹스텝과 공유된 객체는 자동 수정하지 않았습니다."})
            return
        supported = any(is_type(node, base) for base in SUPPORTED_BASES)
        if supported:
            for name in ("its_id", "name"):
                info = field_info(node, name)
                if info and info["required"]:
                    put(node, name, f'auto_{node["typeId"]}_{id}', "generated", "자동 생성한 고유 식별자입니다.")
            if is_type(node, "MachiningWorkingstep"):
                plane(node, "its_secplane", "security_plane_z")
                if request.includePlaceholders:
                    object_field(node, "its_feature", "MachiningFeature", "placeholder", "CAM에 없는 작성용 가공 피처입니다.")
            if is_type(node, "ManufacturingFeature") and request.includePlaceholders:
                object_field(node, "its_workpiece", "Workpiece", "placeholder", "실제 프로젝트 워크피스와 연결되지 않은 임시 워크피스입니다.")
                placement(node, "feature_placement", 0.0)
                plane(node, "depth", "feature_depth_z")
            if is_type(node, "MillingMachiningOperation"):
                object_field(node, "its_technology", "MillingTechnology", "default", "누락된 밀링 기술 객체를 보완했습니다.")
                object_field(node, "its_machine_functions", "MillingMachineFunctions", "default", "누락된 밀링 기계 기능 객체를 보완했습니다.")
            if request.includePlaceholders:
                if is_type(node, "Plane"):
                    placement(node, "position", 0.0)
                if is_type(node, "Axis2Placement3D"):
                    object_field(node, "location", "CartesianPoint", "placeholder", "작성용 임시 좌표입니다.")
                if is_type(node, "CartesianPoint") and id not in original_ids:
                    put(node, "coordinates", [{"itemId": str(uuid4()), "value": 0.0} for _ in range(3)], "placeholder", "작성용 원점 (0,0,0). 실제 좌표가 아닙니다.")
                if is_type(node, "FreeformStrategy"):
                    object_field(node, "its_milling_tolerances", "Tolerances", "placeholder", "작성용 공차 객체입니다.")
            for info in catalog["types"][node["typeId"]]["fields"]:
                name = info["fieldName"]
                if not info["required"] or not missing(node, name):
                    continue
                if name in DEFAULTS:
                    value = request.overrides.get(name, DEFAULTS[name])
                    put(node, name, value, "batch" if name in request.overrides else "default", "사용자 공통 설정" if name in request.overrides else "작성용 기본값이며 실제 CAM 원본값이 아닙니다.")
                elif name in NUMBERS and (request.includePlaceholders or name in request.overrides):
                    put(node, name, request.overrides.get(name, 0.0), "batch" if name in request.overrides else "placeholder", "사용자 공통 설정" if name in request.overrides else "작성용 0 임시값. 실제 치수·공차로 사용하면 안 됩니다.")
        for value in list(node["fields"].values()):
            for item in value if isinstance(value, list) else [value]:
                if ref_id(item):
                    visit(ref_id(item), depth + 1)

    for step in steps:
        visit(step)
    keys = {(entry["nodeId"], entry["fieldName"]) for entry in entries}
    draft["completionEntries"] = [entry for entry in draft["completionEntries"] if (entry["nodeId"], entry["fieldName"]) not in keys] + entries
    if entries:
        draft["revision"] += 1
    try:
        validated = CreatorDraft.model_validate(draft)
    except ValidationError as exc:
        raise CamInputError("보완 후 초안 크기 또는 값 제한을 초과했습니다.") from exc
    return {"draft": validated.model_dump(by_alias=True), "addedCount": len(entries), "skipped": skipped,
            "profileVersion": VERSION, "persisted": False, "machineReady": False}
