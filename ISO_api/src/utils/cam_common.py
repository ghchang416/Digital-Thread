# src/utils/cam_common.py
import re
from typing import Dict, Any, List, Optional
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
        num_blocks.append({"value_component": key, "value_name": str(val)})

    root = {
        "dt_asset": {
            "@xmlns": "http://digital-thread.re/dt_asset",
            "@xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "@schemaVersion": "v30",
            "asset_global_id": global_asset_id_url,
            "asset_kind": "instance",
            "id": asset_id,
            "dt_elements": {
                "@xsi:type": "dt_cutting_tool_13399",
                "element_id": element_id,
                "category": "CuttingTool",  # ✅ 카테고리 강제 삽입
                "display_name": display_name or element_id,
                "numerical_value": (
                    [
                        {
                            "value_component": nb["value_component"],
                            "value_name": nb["value_name"],
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


def ensure_dummy_secplane(ws_node: Dict[str, Any]) -> None:
    """
    Workingstep에 its_secplane, its_secplane.name, its_secplane.position 최소 더미 추가.
    - position은 Axis2Placement3D로 매핑될 그릇만 만들어 둔다(필요 시 나중에 좌표 채움).
    """
    if "its_secplane" not in ws_node or not isinstance(ws_node["its_secplane"], dict):
        ws_node["its_secplane"] = {}

    sec = ws_node["its_secplane"]
    # name 필수
    if not sec.get("name"):
        sec["name"] = "AUTO_SECPLANE"

    # position 필수 (비어 있어도 그릇은 있어야 함)
    if "position" not in sec or not isinstance(sec["position"], dict):
        # Axis2Placement3D에 해당하는 dict 그릇
        # (스키마가 position만 required라면 빈 dict여도 통과. location/axis/ref_direction가 모두 required면 모델을 완화하던가 실제 값을 채워야 함)
        sec["position"] = {}  # {"location": {...}} 등을 나중에 확장 가능


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
