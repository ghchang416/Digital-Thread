# src/utils/cam_nx_adapter.py
from typing import Any, Dict, List

__all__ = ["pick_nx_ops"]


def pick_nx_ops(cam_json: Any) -> List[Dict[str, Any]]:
    """
    NX 계열: cam_json 안에서 operation/steps 리스트를 찾아 반환.
    실제 NX 샘플 구조를 반영해 흔한 키를 우선 탐색.
    """
    if isinstance(cam_json, list):
        return cam_json
    if not isinstance(cam_json, dict):
        return [cam_json]

    for k in ("operations", "ops", "toolpaths", "steps", "items"):
        v = cam_json.get(k)
        if isinstance(v, list):
            return v

    # 못 찾으면 단일 op로 간주
    return [cam_json]
