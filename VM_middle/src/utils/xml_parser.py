# src/utils/xml_parser.py
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple
import re
import xmltodict
from urllib.parse import urlsplit
from datetime import datetime


def _get_by_local(d: dict, local: str):
    if not isinstance(d, dict):
        return None
    if local in d:
        return d[local]
    for k in d.keys():
        if isinstance(k, str) and (
            k.endswith("}" + local) or k.split(":")[-1] == local
        ):
            return d[k]
    return None


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


def _walk_dict(node: Any):
    if isinstance(node, dict):
        for k, v in node.items():
            local = (
                k.split("}", 1)[-1] if (isinstance(k, str) and k.startswith("{")) else k
            )
            yield local, v
            yield from _walk_dict(v)
    elif isinstance(node, list):
        for it in node:
            yield from _walk_dict(it)


def _xsi_local(t: Optional[str]) -> str:
    return (t or "").split(":")[-1]


# ------------------- ID 파싱/정규화 -------------------


def parse_dt_fullpath(fullpath: str) -> Optional[Tuple[str, str, str]]:
    """
    DT_ELEMENT_FULLPATH → (gid, aid, eid) 튜플로 파싱
    예: https://digital-thread.re/kitech/vm_boss_project/prj_001_cutting_tool/T24
        -> ('https://digital-thread.re/kitech/vm_boss_project', 'prj_001_cutting_tool', 'T24')
    스킴 없는 상대경로도 허용.
    """
    if not fullpath or not isinstance(fullpath, str):
        return None

    s = urlsplit(fullpath)
    if s.scheme and s.netloc:
        parts = [p for p in s.path.split("/") if p]
        if len(parts) < 2:
            return None
        eid = parts[-1]
        aid = parts[-2]
        gid = f"{s.scheme}://{s.netloc}" + (
            "/" + "/".join(parts[:-2]) if len(parts) > 2 else ""
        )
        return (gid, aid, eid)
    else:
        parts = [p for p in fullpath.split("/") if p]
        if len(parts) < 2:
            return None
        eid = parts[-1]
        aid = parts[-2]
        gid = "/".join(parts[:-2]) if len(parts) > 2 else ""
        return (gid, aid, eid)


# ------------------- material / project -------------------


def parse_material_xml(xml_text: str) -> Dict[str, Any]:
    """
    dt_material XML에서 display_name, material_identifier, material_property/parameter_name 라인들을
    네임스페이스/리스트/래핑 여부와 무관하게 안전 추출.
    return: {"display_name": str|None, "material_identifier": str|None, "param_lines": List[str]}
    """
    out = {"display_name": None, "material_identifier": None, "param_lines": []}
    if not xml_text or not isinstance(xml_text, str):
        return out

    doc = xmltodict.parse(
        xml_text,
        process_namespaces=True,
        namespaces={
            "http://digital-thread.re/dt_asset": None,
            "http://www.w3.org/2001/XMLSchema-instance": "xsi",
        },
        attr_prefix="@",
        cdata_key="#text",
    )

    dt_asset = _get_by_local(doc, "dt_asset") or {}
    elems = _get_by_local(dt_asset, "dt_elements")
    items = _as_list(elems if elems is not None else [])

    target = None
    for e in items:
        if (
            isinstance(e, dict)
            and (_get_by_local(e, "@xsi:type") or e.get("xsi:type")) == "dt_material"
        ):
            target = e
            break
    if target is None:
        for e in items:
            if isinstance(e, dict):
                dm = _get_by_local(e, "dt_material")
                if isinstance(dm, dict):
                    target = dm
                    break
    if target is None:
        for e in items:
            if isinstance(e, dict):
                target = e
                break

    if isinstance(target, dict):
        # display_name
        dn = _get_by_local(target, "display_name")
        if not isinstance(dn, str):
            for k, v in _walk_dict(target):
                if k == "display_name":
                    dn = (
                        v
                        if isinstance(v, str)
                        else (isinstance(v, dict) and v.get("#text"))
                    ) or None
                    if isinstance(dn, str):
                        dn = dn.strip() or None
                    if dn:
                        break

        # material_identifier
        mi = _get_by_local(target, "material_identifier")
        if not isinstance(mi, str):
            for k, v in _walk_dict(target):
                if k == "material_identifier":
                    mi = (
                        v
                        if isinstance(v, str)
                        else (isinstance(v, dict) and v.get("#text"))
                    ) or None
                    if isinstance(mi, str):
                        mi = mi.strip() or None
                    if mi:
                        break

        # parameter_name 라인 수집
        props = _get_by_local(target, "material_property")
        if props is not None:
            for p in _as_list(props):
                pn = _get_by_local(p, "parameter_name")
                if isinstance(pn, str) and pn.strip():
                    out["param_lines"].append(pn.strip())
                elif isinstance(pn, dict):
                    txt = pn.get("#text")
                    if isinstance(txt, str) and txt.strip():
                        out["param_lines"].append(txt.strip())
        else:
            for k, v in _walk_dict(target):
                if k == "parameter_name":
                    if isinstance(v, str) and v.strip():
                        out["param_lines"].append(v.strip())
                    elif isinstance(v, dict):
                        txt = v.get("#text")
                        if isinstance(txt, str) and txt.strip():
                            out["param_lines"].append(txt.strip())

        out["display_name"] = dn or None
        out["material_identifier"] = mi or None

    return out


def extract_material_ref_from_project_xml(
    project_xml: str,
) -> Optional[Tuple[str, str, str]]:
    """
    its_workpieces/ref_dt_material/keys/value에서 풀패스 찾아 (gid, aid, eid) 반환.
    없으면 element_id만 담아 ("", "", eid).
    """
    if not project_xml:
        return None

    m = re.search(
        r"<its_workpieces>.*?<ref_dt_material>.*?<keys>.*?<value>\s*([^<]+?)\s*</value>.*?</ref_dt_material>.*?</its_workpieces>",
        project_xml,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        fullpath = m.group(1).strip()
        return parse_dt_fullpath(fullpath)

    m2 = re.search(
        r"<its_workpieces>.*?<ref_dt_material>.*?<element_id>\s*([^<]+?)\s*</element_id>",
        project_xml,
        re.DOTALL | re.IGNORECASE,
    )
    if m2:
        return ("", "", m2.group(1).strip())
    return None


# ------------------- workingstep 추출 -------------------


def extract_tool_refs_in_order(
    project_xml: str, wpid: Optional[str]
) -> List[Dict[str, Optional[str]]]:
    """
    main_workplan 또는 지정된 하위 workplan 내부의 워킹스텝을 등장 순서대로 추출.
    반환: [{ ws_id, tool_element_id, tool_fullpath, gid, aid, eid }, ...]
    """
    doc = xmltodict.parse(
        project_xml,
        process_namespaces=True,
        namespaces={
            "http://digital-thread.re/dt_asset": None,
            "http://www.w3.org/2001/XMLSchema-instance": "xsi",
        },
        attr_prefix="@",
        cdata_key="#text",
    )
    dt_asset = _get_by_local(doc, "dt_asset") or doc
    root_elems = _get_by_local(dt_asset, "dt_elements")
    items = root_elems if isinstance(root_elems, list) else [root_elems]

    dt_proj = None
    for e in items:
        if (
            isinstance(e, dict)
            and _xsi_local(e.get("@xsi:type") or e.get("xsi:type")) == "dt_project"
        ):
            dt_proj = e
            break
    if not isinstance(dt_proj, dict):
        return []

    main_wp = _get_by_local(dt_proj, "main_workplan")
    if not isinstance(main_wp, dict):
        return []

    main_id = _get_by_local(main_wp, "its_id")
    elems = _as_list(_get_by_local(main_wp, "its_elements"))

    # 대상 컨테이너 결정
    if not wpid or ((isinstance(main_id, str) and main_id.strip() == wpid.strip())):
        target_container = main_wp
    else:
        target_container = None
        for el in elems:
            ...
            if (_get_by_local(el, "its_id") or "").strip() == wpid.strip():
                target_container = el
                break
        if target_container is None:
            return []

    ws_list = _as_list(_get_by_local(target_container, "its_elements"))

    out: List[Dict[str, Optional[str]]] = []
    for node in ws_list:
        el = node if isinstance(node, dict) else {}
        t = _xsi_local(el.get("@xsi:type") or el.get("xsi:type"))
        if not (t and t.endswith("workingstep")):
            el = el.get("workingstep") or el.get("machining_workingstep") or el
            if not isinstance(el, dict):
                continue

        ws_id = _get_by_local(el, "its_id")
        op = _get_by_local(el, "its_operation")

        tool_eid = None
        tool_full = None
        gid = aid = eid = None

        if isinstance(op, dict):
            ref = _get_by_local(op, "ref_dt_cutting_tool")
            if isinstance(ref, dict):
                tool_eid = _get_by_local(ref, "element_id")
                # keys/value 에서 fullpath
                keys_node = _get_by_local(ref, "keys")
                keys_list = (
                    _as_list(keys_node) if isinstance(keys_node, (list, dict)) else []
                )
                for kv in keys_list:
                    if not isinstance(kv, dict):
                        continue
                    k = _get_by_local(kv, "key")
                    v = _get_by_local(kv, "value")
                    if (
                        isinstance(k, str)
                        and k.strip().upper() == "DT_ELEMENT_FULLPATH"
                    ):
                        tool_full = v
                        break
                if isinstance(tool_full, str):
                    parsed = parse_dt_fullpath(tool_full)
                    if parsed:
                        gid, aid, eid = parsed

        out.append(
            {
                "ws_id": ws_id,
                "tool_element_id": tool_eid,
                "tool_fullpath": tool_full,
                "gid": gid,
                "aid": aid,
                "eid": eid,
            }
        )
    return out


# ------------------- tool / dt_file -------------------


def parse_cutting_tool_13399_xml(tool_xml: str) -> Dict[str, Any]:
    """
    dt_cutting_tool_13399에서 element_id, display_name, numerical_value[value_name -> value_component] 맵 반환.
    """
    doc = xmltodict.parse(
        tool_xml,
        process_namespaces=True,
        namespaces={
            "http://digital-thread.re/dt_asset": None,
            "http://www.w3.org/2001/XMLSchema-instance": "xsi",
        },
        attr_prefix="@",
        cdata_key="#text",
    )
    dt_asset = _get_by_local(doc, "dt_asset") or doc
    elems = _get_by_local(dt_asset, "dt_elements")
    if not isinstance(elems, dict):
        return {}
    if (
        _xsi_local(elems.get("@xsi:type") or elems.get("xsi:type"))
        != "dt_cutting_tool_13399"
    ):
        return {}

    element_id = _get_by_local(elems, "element_id")
    display_name = _get_by_local(elems, "display_name")
    values = {}
    for nv in _as_list(_get_by_local(elems, "numerical_value")):
        if not isinstance(nv, dict):
            continue
        name = _get_by_local(nv, "value_name")
        val = _get_by_local(nv, "value_component")
        if name is not None:
            try:
                values[name] = float(val)
            except (TypeError, ValueError):
                values[name] = None
    return {"element_id": element_id, "display_name": display_name, "values": values}


def pick_tool_fields_13399(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    필요한 필드만 dict로 반환.
    """

    def find(name: str) -> Optional[float]:
        for nv in parsed.get("numerical_values", []):
            if (
                isinstance(nv, dict)
                and (nv.get("name") or "").strip().lower() == name.strip().lower()
            ):
                return nv.get("value")
        return None

    eff = find("effective_cutting_diameter")
    corner = find("corner_radius")
    func_len = find("functional_length")
    overhang = find("overhang_length")
    teeth = find("number_of_teeth")

    return {
        "effective_cutting_diameter": eff,
        "corner_radius": corner,
        "functional_length": func_len,
        "overhang_length": overhang,
        "number_of_teeth": teeth,
    }


def parse_dt_file_xml(xml_text: str) -> Dict[str, Any]:
    """
    dt_file XML에서 필요한 값 추출:
    - element_id, display_name
    - content_oid: <value> (GridFS/ObjectId)
    - refs: {DT_GLOBAL_ASSET, DT_ASSET, DT_PROJECT, WORKPLAN}
    """
    doc = xmltodict.parse(
        xml_text,
        process_namespaces=True,
        namespaces={
            "http://digital-thread.re/dt_asset": None,
            "http://www.w3.org/2001/XMLSchema-instance": "xsi",
        },
        attr_prefix="@",
        cdata_key="#text",
    )
    dt_asset = _get_by_local(doc, "dt_asset") or {}
    item = _get_by_local(dt_asset, "dt_elements") or {}

    element_id = _get_by_local(item, "element_id")
    display_name = _get_by_local(item, "display_name")
    content_oid = _get_by_local(item, "value")  # <value>69030ba1a9...>

    refs: Dict[str, Optional[str]] = {
        "DT_GLOBAL_ASSET": None,
        "DT_ASSET": None,
        "DT_PROJECT": None,
        "WORKPLAN": None,
    }

    ref = _get_by_local(item, "reference")
    if isinstance(ref, dict):
        keys = _get_by_local(ref, "keys")
        keys_list = (
            keys if isinstance(keys, list) else [keys] if isinstance(keys, dict) else []
        )
        for kv in keys_list:
            if not isinstance(kv, dict):
                continue
            k = _get_by_local(kv, "key")
            v = _get_by_local(kv, "value")
            if isinstance(k, str) and k in refs:
                txt = (
                    (v.get("#text") if isinstance(v, dict) else v)
                    if v is not None
                    else None
                )
                refs[k] = (txt or "").strip() if isinstance(txt, str) else None

    return {
        "element_id": element_id,
        "display_name": display_name,
        "content_oid": (
            (content_oid or "").strip() if isinstance(content_oid, str) else None
        ),
        "refs": refs,
    }


def match_dt_file_refs(
    parsed: Dict[str, Any],
    *,
    gid: str,
    aid: str,
    eid: str,
    wpid: Optional[str] = None,
) -> bool:
    refs = (parsed or {}).get("refs") or {}
    if (refs.get("DT_GLOBAL_ASSET") or "") != (gid or ""):
        return False
    if (refs.get("DT_ASSET") or "") != (aid or ""):
        return False
    if (refs.get("DT_PROJECT") or "") != (eid or ""):
        return False
    if wpid:
        return (refs.get("WORKPLAN") or "") == wpid
    return True


def make_vm_dt_file_xml(
    *,
    asset_global_id: str,
    vm_asset_id: str,  # 예: "vm_001"
    download_file_link: str,  # VM에서 받은 S3 URL
    gid: str,  # DT_GLOBAL_ASSET (원본 프로젝트 gid)
    aid: str,  # DT_ASSET (원본 프로젝트 aid)
    eid: str,  # DT_PROJECT (원본 프로젝트 eid)
    wpid: Optional[str],  # WORKPLAN (없으면 빈 문자열)
    seq_id: int,  # 기존 SEQ_ID + 1 또는 1
    now: Optional[datetime] = None,
) -> str:
    """
    VM DT_FILE용 XML 생성.
    - DATE 형식: YYYYMMDD HHMMSS → 예: 20251028 092000
    """
    now = now or datetime.now()
    date_str = now.strftime("%Y%m%d %H%M%S")
    wpid_val = wpid or ""

    # vm dt_file 예시 구조에 맞춰 생성
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<dt_asset xmlns="http://digital-thread.re/dt_asset"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          schemaVersion="v31">
  <asset_global_id>{asset_global_id}</asset_global_id>
  <id>{vm_asset_id}</id>
  <asset_kind>instance</asset_kind>
  <dt_elements xsi:type="dt_file">
    <element_id>{vm_asset_id}</element_id>
    <category>VM</category>
    <display_name></display_name>
    <element_description>vm result file.</element_description>
    <content_type>application/zip</content_type>
    <value></value>
    <path>{download_file_link}</path>
    <reference>
      <element_id></element_id>
      <keys>
        <key>DT_GLOBAL_ASSET</key>
        <value>{gid}</value>
      </keys>
      <keys>
        <key>DT_ASSET</key>
        <value>{aid}</value>
      </keys>
      <keys>
        <key>DT_PROJECT</key>
        <value>{eid}</value>
      </keys>
      <keys>
        <key>WORKPLAN</key>
        <value>{wpid_val}</value>
      </keys>
    </reference>
    <properties>
      <key>NO_CODE</key>
      <value>{vm_asset_id}</value>
    </properties>
    <properties>
      <key>SEQ_ID</key>
      <value>{seq_id}</value>
    </properties>
    <properties>
      <key>Date</key>
      <value>{date_str}</value>
    </properties>
  </dt_elements>
</dt_asset>
"""
    return xml
