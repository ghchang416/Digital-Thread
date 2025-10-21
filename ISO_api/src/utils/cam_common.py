# src/utils/cam_common.py
import re
from typing import Dict, Any, List, Optional
from collections import OrderedDict
from src.utils.cam_nx_adapter import pick_nx_ops
from src.utils.cam_powermill_adapter import pick_powermill_ops
from src.utils.v3_xml_parser import get_nested_value
import xmltodict

__all__ = [
    "F14649_TO_13399",
    "invert_cam14649_to_cam13399",
    "extract_13399_values_from_cam",
    "build_cutting_tool_13399_dtasset_xml",
    "pick_ops",
]

_ELEM_ID_SAFE = re.compile(r"[^0-9A-Za-z_\-]")

# 14649 경로 → 13399 컴포넌트명 매핑 (NX/파워밀 공용)
F14649_TO_13399: Dict[str, str] = {
    # 지름
    "MachiningWorkingstep.its_operation.MachiningOperation.its_tool.MachiningTool.MillingMachineCuttingTool.effective_cutting_diameter": "effective_cutting_diameter",
    # 코너 R
    "MachiningWorkingstep.its_operation.MachiningOperation.its_tool.MachiningTool.MillingMachineCuttingTool.MillingCuttingTool.edge_radius": "corner_radius",
    # 가공부 길이
    "MachiningWorkingstep.its_operation.MachiningOperation.its_tool.MachiningTool.MillingMachineCuttingTool.its_cutting_edges.CuttingComponent.tool_functional_length": "functional_length",
    # 오버행(툴 돌출)
    "MachiningWorkingstep.its_operation.MachiningOperation.its_tool.MachiningTool.MillingMachineCuttingTool.overall_assembly_length": "overhang_length",
    # 날 수(Z)
    "MachiningWorkingstep.its_operation.MachiningOperation.its_tool.MachiningTool.MillingMachineCuttingTool.MillingCuttingTool.number_of_effective_teeth": "number_of_teeth",
}

DEFAULT_SCHEMA_VERSION = "v31"


def invert_cam14649_to_cam13399(cam_to_14649_map: Dict[str, str]) -> Dict[str, str]:
    """
    CAM키 -> 14649경로 (매핑파일) + 14649경로 -> 13399컴포넌트 (상수 dict)
    를 합성해서, CAM키 -> 13399컴포넌트 로 변환 테이블을 만든다.
    """
    cam_to_13399: Dict[str, str] = {}
    for cam_key, path_14649 in cam_to_14649_map.items():
        comp = F14649_TO_13399.get(path_14649)
        if comp:
            cam_to_13399[cam_key] = comp
    return cam_to_13399


def extract_13399_values_from_cam(
    cam_obj: Dict[str, Any], cam_to_13399_map: Dict[str, str]
) -> Dict[str, Any]:
    """CAM JSON + 'CAM키 → 13399컴포넌트' 매핑으로 13399 값들 추출"""
    out: Dict[str, Any] = {}
    for cam_key, comp in cam_to_13399_map.items():
        keys = cam_key.split(".")  # "a.b.c" → ["a","b","c"]
        v = get_nested_value(cam_obj, keys)
        if v is not None and v != "":
            out[comp] = v
    return out


def build_cutting_tool_13399_dtasset_xml(
    *,
    global_asset_id_url: str,
    asset_id: str,
    element_id: str,
    display_name: str,
    values_13399: Dict[str, Any],
) -> str:
    """
    13399 dt_asset XML 생성 (요청 포맷)
    """
    num_blocks = []
    for key in (
        "effective_cutting_diameter",
        "corner_radius",
        "functional_length",
        "overhang_length",
        "number_of_teeth",
    ):
        val = values_13399.get(key)
        if val is None or val == "":
            continue
        # 🔁 여기서 '이름/값'을 서로 바꿔서 넣는다
        num_blocks.append({"value_name": key, "value_component": str(val)})

    root = {
        "dt_asset": {
            "@xmlns": "http://digital-thread.re/dt_asset",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@schemaVersion": DEFAULT_SCHEMA_VERSION,
            "asset_global_id": global_asset_id_url,
            "id": asset_id,
            "asset_kind": "instance",
            "dt_elements": {
                "@xsi:type": "dt_cutting_tool_13399",
                "element_id": element_id,
                "category": "CuttingTool",  # ✅ 카테고리 강제 삽입
                "display_name": display_name or element_id,
                "numerical_value": (
                    [
                        {
                            "value_name": nb["value_name"],
                            "value_component": nb["value_component"],
                        }
                        for nb in num_blocks
                    ]
                    if num_blocks
                    else None
                ),
            },
        }
    }
    if not root["dt_asset"]["dt_elements"]["numerical_value"]:
        root["dt_asset"]["dt_elements"].pop("numerical_value", None)
    return xmltodict.unparse(root, pretty=True, attr_prefix="@")


def pick_ops(cam_type: str, cam_json: Any) -> List[Dict[str, Any]]:
    """
    CAM 타입별로 파일 안에서 operation list를 추출.
    - NX: 1 파일에 다수 op
    - PowerMILL: 보통 파일 당 1 op (but 방어적으로 리스트 반환)
    """
    t = (cam_type or "").lower()
    if t == "nx":
        return pick_nx_ops(cam_json)
    if t in ("powermill", "pmill", "power_mill"):
        return pick_powermill_ops(cam_json)
    # 기타: best-effort
    return cam_json if isinstance(cam_json, list) else [cam_json]


def ensure_dummy_secplane(ws_node: Dict[str, Any], idx: int = 1) -> None:
    """
    Workingstep에 its_secplane 최소 구조 보강.
    - secplane-001, pos-001 같은 식으로 넘버링
    - 위치는 origin(0,0,0) 좌표 기본값
    """
    if "its_secplane" not in ws_node or not isinstance(ws_node["its_secplane"], dict):
        ws_node["its_secplane"] = {}

    sec = ws_node["its_secplane"]

    # name 필수
    if not sec.get("name"):
        sec["name"] = f"secplane-{idx:03d}"

    # position 필수 (Axis2Placement3D 구조)
    if "position" not in sec or not isinstance(sec["position"], dict):
        sec["position"] = {}

    pos = sec["position"]
    if not pos.get("name"):
        pos["name"] = f"pos-{idx:03d}"

    if "location" not in pos or not isinstance(pos["location"], dict):
        pos["location"] = {}

    loc = pos["location"]
    if not loc.get("name"):
        loc["name"] = "origin"
    if "coordinates" not in loc:
        # 기본 좌표 0,0,0
        loc["coordinates"] = ["0.0", "0.0", "0.0"]


def ensure_dummy_feature(ws_node: Dict[str, Any]) -> None:
    """
    Workingstep에 its_feature 최소 더미 추가.
    - its_id, its_workpiece(최소 its_id)만 채운다.
    """
    if "its_feature" not in ws_node or not isinstance(ws_node["its_feature"], dict):
        ws_node["its_feature"] = {}

    feat = ws_node["its_feature"]
    if not feat.get("its_id"):
        feat["its_id"] = "auto_feature"

    # its_workpiece: 스키마가 참조형이면 실제 워크피스 존재가 이상적이나,
    # 일단 최소 구조로 its_id만 더미로 채운다. (프로젝트에 진짜 워크피스가 없다면
    # 나중에 전용 API로 보강하는 게 정석)
    if "its_workpiece" not in feat or not isinstance(feat["its_workpiece"], dict):
        feat["its_workpiece"] = {"its_id": "default_workpiece"}


def ensure_feedrate_reference(
    ws_node: Dict[str, Any], cutmode: str | None = None
) -> None:
    """
    its_operation.its_technology.feedrate_reference를 보장.
    - cutmode가 'climb'이면 FEED_PER_TOOTH(=CCP), 'conventional'이면 FEED_PER_REV(=TCP) 같은 내부 규칙 적용 가능.
      (조직 룰에 맞게 조정해도 됨)
    """
    op = ws_node.get("its_operation")
    if not isinstance(op, dict):
        op = {}
        ws_node["its_operation"] = op

    tech = op.get("its_technology")
    if not isinstance(tech, dict):
        tech = {}
        op["its_technology"] = tech

    # 이미 값이 있으면 그대로 둠
    if tech.get("feedrate_reference"):
        return

    # 기본 규칙: climb → FEED_PER_TOOTH, conventional → FEED_PER_REV
    ref = None
    if cutmode:
        cm = str(cutmode).strip().lower()
        if cm == "climb":
            ref = "ccp"  # CCP
        elif cm == "conventional":
            ref = "tcp"  # TCP

    # 혹시 cutmode 못 찾으면 안전 기본값
    tech["feedrate_reference"] = ref or "tcp"


def derive_tool_element_id_from_mapping(
    cam_op: Dict[str, any],
    cam_to_14649_map: Dict[str, str],
    fallback_elem_id: str,
) -> str:
    """
    CAM op에서 매핑 상 '...MachiningTool.its_id' 로 연결되는 CAM 키를 찾아
    그 값을 tool의 element_id로 사용.
    - 값이 없거나 공백이면 fallback 사용
    - element_id: 공백 → '_' 치환
    - 허용되지 않은 특수문자는 '_' 로 치환
    """
    # 매핑에서 MachiningTool.its_id 로 끝나는 항목을 찾는다.
    source_cam_key: Optional[str] = None
    for cam_key, path in cam_to_14649_map.items():
        if (
            path.endswith(
                "MachiningWorkingstep.its_operation.MachiningOperation.its_tool.MachiningTool.its_id"
            )
            or path.endswith("MachiningOperation.its_tool.MachiningTool.its_id")
            or path.endswith("MachiningTool.its_id")
        ):
            source_cam_key = cam_key
            break

    if not source_cam_key:
        return fallback_elem_id

    # 값 추출
    raw = get_nested_value(cam_op, source_cam_key.split("."))
    if raw is None:
        return fallback_elem_id

    val = str(raw).strip()
    if not val:
        return fallback_elem_id

    # 공백 → 언더스코어
    val = val.replace(" ", "_")

    # 나머지 unsafe 문자들 → '_'
    safe = _ELEM_ID_SAFE.sub("_", val)

    return safe


def derive_tool_display_name_from_mapping(
    cam_op: Dict[str, Any],
    cam_to_14649_map: Dict[str, str],
    fallback_display: str,
) -> str:
    """
    CAM op에서 매핑 상 '...MachiningTool.its_id' 로 연결되는 CAM 키를 찾아
    그 값을 tool의 display_name 으로 사용.
    - 값이 없거나 공백이면 fallback 사용
    """
    source_cam_key: Optional[str] = None
    for cam_key, path in cam_to_14649_map.items():
        if (
            path.endswith(
                "MachiningWorkingstep.its_operation.MachiningOperation.its_tool.MachiningTool.its_id"
            )
            or path.endswith("MachiningOperation.its_tool.MachiningTool.its_id")
            or path.endswith("MachiningTool.its_id")
        ):
            source_cam_key = cam_key
            break

    if not source_cam_key:
        return fallback_display

    # 기존에 쓰던 get_nested_value 재사용
    from src.utils.v3_xml_parser import get_nested_value  # 위치는 프로젝트 구조에 맞게

    raw = get_nested_value(cam_op, source_cam_key.split("."))
    if raw is None:
        return fallback_display

    val = str(raw).strip()
    return val if val else fallback_display


def ensure_dummy_its_tool(ws_node: Dict[str, Any], dummy_id: str = "temp") -> None:
    op = ws_node.setdefault("its_operation", {})
    its_tool = op.get("its_tool")
    if not isinstance(its_tool, dict):
        op["its_tool"] = {"@xsi:type": "machining_tool", "its_id": dummy_id}
    else:
        its_tool.setdefault("@xsi:type", "machining_tool")
        its_tool.setdefault("its_id", dummy_id)


def force_dummy_its_tool(ws_node: Dict[str, Any], dummy_id: str = "temp") -> None:
    """
    its_operation 직하 혹은 래핑(MachiningOperation) 내부 어디든
    its_tool을 '더미'로 **강제 교체**한다.
    """
    if not isinstance(ws_node, dict):
        return

    op = ws_node.get("its_operation")
    if not isinstance(op, dict):
        op = {}
        ws_node["its_operation"] = op

    mo = op.get("MachiningOperation") or op.get("machining_operation")
    target = mo if isinstance(mo, dict) else op

    # 🔥 무조건 덮어쓰기
    target["its_tool"] = {"@xsi:type": "machining_tool", "its_id": dummy_id}


def ensure_milling_technology(
    ws_node: Dict[str, Any], cutmode: str | None = None
) -> None:
    """
    its_operation.its_technology (milling_technology) 보강:
    - feedrate_reference: cutmode 값(climb/conventional)에 따라 보강 (없으면 tcp 기본값)
    - spindle/feedrate는 CAM JSON에서 이미 있으면 유지
    - 필수 필드(synchronize_spindle_with_feed, inhibit_feedrate_override, inhibit_spindle_override) 누락 시 false 채움
    - XML 내 순서를 스키마 정의 순서대로 재정렬
      feedrate → feedrate_reference → spindle → synchronize_spindle_with_feed
      → inhibit_feedrate_override → inhibit_spindle_override
    """
    op = ws_node.setdefault("its_operation", {})
    tech = op.get("its_technology")
    if not isinstance(tech, dict):
        tech = {}
        op["its_technology"] = tech

    # feedrate_reference 보강 (cutmode 기반)
    if not tech.get("feedrate_reference"):
        ref = None
        if cutmode:
            cm = str(cutmode).strip().lower()
            if cm == "climb":
                ref = "ccp"
            elif cm == "conventional":
                ref = "tcp"
        tech["feedrate_reference"] = ref or "tcp"

    # 필수 필드 보강
    if "synchronize_spindle_with_feed" not in tech:
        tech["synchronize_spindle_with_feed"] = False
    if "inhibit_feedrate_override" not in tech:
        tech["inhibit_feedrate_override"] = False
    if "inhibit_spindle_override" not in tech:
        tech["inhibit_spindle_override"] = False

    # 🔑 순서 재정렬 + @xsi:type 보존
    ordered: Dict[str, Any] = {}

    # 1) 있으면 타입을 맨 앞에 보존
    if "@xsi:type" in tech and tech["@xsi:type"]:
        ordered["@xsi:type"] = tech["@xsi:type"]

    # 2) 스키마 순서대로 요소 정렬
    for key in [
        "feedrate",
        "feedrate_reference",
        "spindle",
        "synchronize_spindle_with_feed",
        "inhibit_feedrate_override",
        "inhibit_spindle_override",
    ]:
        if key in tech:
            ordered[key] = tech[key]

    # 3) 누락된 기타 키(확장 필드 등) 뒤에 보존
    for k, v in tech.items():
        if k not in ordered:
            ordered[k] = v

    op["its_technology"] = ordered


def _normalize_bool_like(raw, *, default=False) -> bool:
    """
    다양한 CAM 표현(문자/숫자/불리언)을 bool로 정규화.
    """
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return bool(default)
    if isinstance(raw, (int, float)):
        return raw > 0
    s = str(raw).strip().lower()
    if not s:
        return bool(default)
    truthy = {
        "standard",
        "flood",
        "mist",
        "air",
        "through",
        "thru",
        "high_pressure",
        "highpressure",
        "on",
        "true",
        "yes",
    }
    falsy = {"none", "off", "false", "no", "0"}
    if s in truthy or s.startswith("through"):
        return True
    if s in falsy:
        return False
    return bool(default)


def ensure_milling_machine_functions(
    ws_node: dict, raw_coolant=None, *, default=False
) -> None:
    """
    Workingstep(dict: its_elements 한 블록) 안에 있는
    its_operation → its_machine_functions(milling_machine_functions) 를 보강한다.

    - coolant(Required), through_spindle_coolant(Required), chip_removal(Required)를 보장
    - coolant가 True면 나머지(required 2개)도 True로 끌어올림
    - @xsi:type="milling_machine_functions" 보장
    - 가능한 필드 출력 순서를 스키마 순서에 가깝게 재정렬
    """
    if not isinstance(ws_node, dict):
        return

    op = ws_node.setdefault("its_operation", {})
    mf = op.get("its_machine_functions")
    if not isinstance(mf, dict):
        mf = {}
        op["its_machine_functions"] = mf

    # 타입 보정
    mf["@xsi:type"] = "milling_machine_functions"

    # 기존 coolant 값을 우선 존중하되, 없으면 raw_coolant 로부터 정규화
    if "coolant" in mf and isinstance(mf["coolant"], bool):
        coolant_bool = mf["coolant"]
    else:
        coolant_bool = _normalize_bool_like(raw_coolant, default=default)
        mf["coolant"] = coolant_bool

    # 필수 항목 채우기
    # coolant가 True면 나머지 두 필수도 True로 끌어올림
    if coolant_bool:
        mf["through_spindle_coolant"] = True
        mf["chip_removal"] = True
    else:
        # 기존 값이 있으면 유지, 없으면 False 채움
        mf["through_spindle_coolant"] = bool(mf.get("through_spindle_coolant", False))
        mf["chip_removal"] = bool(mf.get("chip_removal", False))

    # ---- 출력 순서 정돈(선택) ----
    # 스키마 정의 순서에 맞춰 새 dict 구성 (있을 때만 포함)
    order = [
        "@xsi:type",
        "coolant",
        "coolant_pressure",
        "mist",
        "through_spindle_coolant",
        "through_pressure",
        "axis_clamping",
        "chip_removal",
        "oriented_spindle_stop",
        "its_process_model",
        "other_functions",
    ]
    ordered = {}
    for k in order:
        if k in mf:
            ordered[k] = mf[k]
    # 혹시 누락된 키가 있으면 뒤에 붙임
    for k, v in mf.items():
        if k not in ordered:
            ordered[k] = v

    op["its_machine_functions"] = ordered


def find_cam_key_for_coolant(cam_to_14649_map: dict) -> str | None:
    """
    매핑에서 '...MillingMachineFunctions.coolant' 로 끝나는 CAM 키를 찾아준다.
    경로가 프로젝트마다 조금씩 다를 수 있어서 여러 패턴을 순서대로 탐색.
    """
    suffixes = [
        "MillingMachineFunctions.coolant",
        "MachineFunctions.MillingMachineFunctions.coolant",
        "its_machine_functions.MillingMachineFunctions.coolant",
        "its_machine_functions.MachineFunctions.MillingMachineFunctions.coolant",
        ".coolant",  # 최후의 폴백
    ]
    for suf in suffixes:
        for cam_key, path in cam_to_14649_map.items():
            if path.endswith(suf):
                return cam_key
    return None


def ensure_strategy_with_pathmode(
    ws_node: dict,
    cam_op: dict,
    cam_to_14649_map: dict,
    default: str = "forward",
) -> None:
    """
    its_machining_strategy 내에 pathmode를 보장하고,
    pathmode가 cutmode보다 먼저 직렬화되도록 키 순서를 정리한다.
    - CAM 매핑에 FreeformStrategy.pathmode가 있으면 CAM 값을 우선 사용
    - 없거나 빈 값이면 default("forward") 사용
    """
    if not isinstance(ws_node, dict):
        return

    op = ws_node.setdefault("its_operation", {})
    strat = op.get("its_machining_strategy")
    if not isinstance(strat, dict):
        strat = {}
        op["its_machining_strategy"] = strat

    # CAM 매핑에서 pathmode 소스 키 찾기
    pathmode_cam_key = None
    for cam_key, path in cam_to_14649_map.items():
        if (
            path.endswith("its_machining_strategy.FreeformStrategy.pathmode")
            or path.endswith("FreeformStrategy.pathmode")
            or path.endswith(".pathmode")
        ):
            pathmode_cam_key = cam_key
            break

    # CAM 값 추출 -> 없으면 default
    if pathmode_cam_key:
        raw = get_nested_value(cam_op, pathmode_cam_key.split("."))
    else:
        raw = None

    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        pathmode_val = default
    else:
        pathmode_val = str(raw).strip()

    # 값 주입
    strat["pathmode"] = pathmode_val

    # 순서 재정렬: (@xsi:type) → its_milling_tolerances → pathmode → cutmode → stepover → 기타
    desired_order = [
        "@xsi:type",
        "its_milling_tolerances",
        "pathmode",
        "cutmode",
        "stepover",
    ]
    ordered = {}
    for k in desired_order:
        if k in strat:
            ordered[k] = strat[k]
    for k, v in strat.items():
        if k not in ordered:
            ordered[k] = v

    op["its_machining_strategy"] = ordered


def reorder_operation_children(op: dict) -> dict:
    """
    its_operation 내부 element 순서를 스키마 요구대로 재정렬한다.
    - ref_dt_cutting_tool → its_id → its_tool → its_technology →
      its_machine_functions → its_machining_strategy → 기타
    """
    if not isinstance(op, dict):
        return op

    desired_order = [
        "ref_dt_cutting_tool",
        "its_id",
        "its_tool",
        "its_technology",
        "its_machine_functions",
        "its_machining_strategy",
    ]

    ordered = {}
    for k in desired_order:
        if k in op:
            ordered[k] = op[k]

    # 나머지 키도 보존
    for k, v in op.items():
        if k not in ordered:
            ordered[k] = v

    return ordered


def normalize_dt_project_structure(xml_text: str, project_element_id: str) -> str:
    """
    dt_project 전체 구조/순서를 한 번에 정리하여 XSD 순서 제약을 만족시키는 유틸.
    - 루트(dt_asset) 일부 키와 dt_project / main_workplan / workingstep / operation / 내부 서브블록 순서까지 정리
    - 입력: XML 문자열, 대상 project element_id
    - 출력: 정렬된 XML 문자열
    """

    def _ordered(d: Dict[str, Any], prefer_keys: List[str]) -> "OrderedDict[str, Any]":
        od = OrderedDict()
        for k in prefer_keys:
            if k in d:
                od[k] = d[k]
        for k, v in d.items():
            if k not in od:
                od[k] = v
        return od

    def _normalize_root(dt_asset: Dict[str, Any]) -> None:
        # 루트 속성 보존
        # dt_asset 순서: (attributes) → asset_global_id → asset_kind → id → dt_elements → 나머지
        keys = list(dt_asset.keys())
        attrs = OrderedDict((k, dt_asset[k]) for k in keys if k.startswith("@"))
        body = {k: dt_asset[k] for k in keys if not k.startswith("@")}
        ordered = OrderedDict()
        ordered.update(attrs)
        for k in ("asset_global_id", "id", "asset_kind", "dt_elements"):
            if k in body:
                ordered[k] = body.pop(k)
        # 남은 키 붙이기
        for k, v in body.items():
            ordered[k] = v
        dt_asset.clear()
        dt_asset.update(ordered)

    def _normalize_strategy(strat: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(strat, dict):
            return strat
        # tolerances 내부
        tol = strat.get("its_milling_tolerances")
        if isinstance(tol, dict):
            strat["its_milling_tolerances"] = _ordered(
                tol, ["chordal_tolerance", "scallop_height"]
            )
        # strategy 내부 순서
        return _ordered(
            strat, ["pathmode", "cutmode", "its_milling_tolerances", "stepover"]
        )

    def _normalize_technology(tech: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(tech, dict):
            return tech
        return _ordered(
            tech,
            [
                "feedrate",
                "feedrate_reference",
                "spindle",
                "synchronize_spindle_with_feed",
                "inhibit_feedrate_override",
                "inhibit_spindle_override",
            ],
        )

    def _normalize_operation(op: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(op, dict):
            return op
        # 내부 블록들 먼저 정리
        if "its_technology" in op and isinstance(op["its_technology"], dict):
            op["its_technology"] = _normalize_technology(op["its_technology"])
        if "its_machining_strategy" in op and isinstance(
            op["its_machining_strategy"], dict
        ):
            op["its_machining_strategy"] = _normalize_strategy(
                op["its_machining_strategy"]
            )
        # operation 자식 순서
        return _ordered(
            op,
            [
                "ref_dt_cutting_tool",
                "its_id",
                "its_tool",
                "its_technology",
                "its_machine_functions",
                "its_machining_strategy",
            ],
        )

    def _normalize_workingstep(ws: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(ws, dict):
            return ws
        # its_operation 내부 먼저 정리
        if "its_operation" in ws and isinstance(ws["its_operation"], dict):
            ws["its_operation"] = _normalize_operation(ws["its_operation"])
        # workingstep 자식 순서
        return _ordered(
            ws, ["its_id", "its_secplane", "its_feature", "its_operation", "its_effect"]
        )

    def _normalize_main_workplan(wp: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(wp, dict):
            return wp
        # its_elements → 리스트/단일 모두 대응하여 ws 정리
        elems = wp.get("its_elements")
        if elems is not None:
            if isinstance(elems, list):
                wp["its_elements"] = [_normalize_workingstep(e) for e in elems]
            elif isinstance(elems, dict):
                wp["its_elements"] = _normalize_workingstep(elems)
        # main_workplan 자식 순서: its_id → its_elements → ref_dt_machine_tool → 기타
        return _ordered(wp, ["its_id", "its_elements", "ref_dt_machine_tool"])

    def _normalize_workpieces_container(wp: Dict[str, Any]) -> Dict[str, Any]:
        """
        its_workpieces 내부의 기존 키 순서를 그대로 유지하되,
        ref_dt_material만 맨 마지막으로 이동시킨다.
        """
        if not isinstance(wp, dict):
            return wp

        if "ref_dt_material" not in wp:
            return wp  # ref_dt_material이 없으면 그대로 반환

        val_ref = wp.pop("ref_dt_material")

        # ⚙️ 기존 순서 유지 (파이썬 3.7+ dict 순서 보장)
        ordered = OrderedDict(wp)

        # ref_dt_material만 맨 뒤로 추가
        ordered["ref_dt_material"] = val_ref
        return ordered

    # --- 파싱 ---
    doc = xmltodict.parse(xml_text)
    dt_asset = doc.get("dt_asset")
    if not isinstance(dt_asset, dict):
        return xml_text

    # 루트 정리
    _normalize_root(dt_asset)

    proj = dt_asset.get("dt_elements")
    if not isinstance(proj, dict):
        return xml_text
    # 대상 프로젝트만 정리
    if proj.get("@xsi:type") and proj["@xsi:type"] != "dt_project":
        return xml_text
    if proj.get("element_id") != project_element_id:
        return xml_text

    # main_workplan 정리
    if "main_workplan" in proj and isinstance(proj["main_workplan"], dict):
        proj["main_workplan"] = _normalize_main_workplan(proj["main_workplan"])

    # its_workpieces 내부는 순서 제약이 상대적으로 느슨하지만, 기본 키 순서만 정리
    if "its_workpieces" in proj:
        wps = proj["its_workpieces"]
        if isinstance(wps, list):
            proj["its_workpieces"] = [_normalize_workpieces_container(w) for w in wps]
        elif isinstance(wps, dict):
            proj["its_workpieces"] = _normalize_workpieces_container(wps)

    # dt_project 자식 전체 순서 정리
    proj_order = [
        "element_id",
        "category",
        "display_name",
        "element_description",
        "its_id",
        "main_workplan",
        "its_workpieces",
    ]
    dt_asset["dt_elements"] = _ordered(proj, proj_order)

    # --- 직렬화 ---
    return xmltodict.unparse(doc, pretty=True)
