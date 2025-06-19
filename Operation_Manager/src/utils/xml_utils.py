# src/utils/xml_utils.py

import xmltodict

def xml_to_dict(xml_string: str) -> dict:
    """
    XML 문자열을 dict로 변환하며, None 값은 빈 리스트로 치환.

    :param xml_string: XML 포맷 문자열
    :return: 파싱된 dict
    """
    project_dict = xmltodict.parse(xml_string)
    return replace_none_with_empty_list(project_dict)

def extract_its_id(xml_string: str) -> str:
    """
    프로젝트 XML에서 its_id(프로젝트 식별자) 추출.

    :param xml_string: 프로젝트 XML
    :return: its_id (없으면 "unknown")
    """
    try:
        data = xml_to_dict(xml_string)
        return data["project"]["its_id"]
    except Exception:
        return "unknown"

def extract_workplans_with_nc(data: dict) -> list:
    """
    main_workplan 및 its_elements에 포함된 모든 workplan 객체 추출.

    :param data: 전체 XML dict 데이터
    :return: workplan dict 리스트
    """
    main_workplan = data["project"].get("main_workplan")
    results = []
    if main_workplan.get("its_id"):
        results.append(main_workplan)
    its_elements = main_workplan.get("its_elements")
    if its_elements:
        if not isinstance(its_elements, list):
            its_elements = [its_elements]
        for element in its_elements:
            # 타입이 workplan이고 its_id가 있는 경우만 포함
            if isinstance(element, dict) and element.get("@xsi:type") == "workplan" and element.get("its_id"):
                results.append(element)
    return results

def extract_nc_id(workplan: dict) -> str:
    """
    workplan dict에서 nc_code의 its_id 추출.

    :param workplan: workplan dict
    :return: nc_code의 its_id (없으면 None/unknown)
    """
    nc_code = workplan.get("nc_code", {})
    if isinstance(nc_code, dict):
        return nc_code.get("its_id", "unknown")
    return None

def verify_nc_code_in_workplan(data_dict: dict, workplan_id: str, nc_code_id: str) -> bool:
    """
    특정 workplan에 nc_code_id가 존재하는지 검증.

    :param data_dict: 전체 XML dict
    :param workplan_id: 검사 대상 workplan의 its_id
    :param nc_code_id: nc_code의 its_id
    :return: 존재 여부(bool)
    """
    main_workplan = data_dict['project'].get("main_workplan")
    if not main_workplan:
        return False
    elements = main_workplan.get("its_elements", [])
    if not isinstance(elements, list):
        elements = [elements]
    for element in elements:
        if element.get("@xsi:type") == "workplan" and element.get("its_id") == workplan_id:
            nc_codes = element.get("nc_code", [])
            if isinstance(nc_codes, dict):
                nc_codes = [nc_codes]
            return any(nc.get("its_id") == nc_code_id for nc in nc_codes)
    # main_workplan 자체가 해당 workplan일 경우도 체크
    if main_workplan.get("its_id") == workplan_id:
        nc_codes = main_workplan.get("nc_code", [])
        if isinstance(nc_codes, dict):
            nc_codes = [nc_codes]
        return any(nc.get("its_id") == nc_code_id for nc in nc_codes)
    return False

def update_nc_code_id_in_workplan(
    data: dict, workplan_id: str, new_nc_code_id: str, prev_nc_code_id: str
) -> bool:
    """
    특정 workplan 내 nc_code의 its_id를 prev에서 new로 업데이트.

    :param data: 전체 XML dict
    :param workplan_id: 수정할 workplan의 its_id
    :param new_nc_code_id: 새로 반영할 nc_code의 its_id
    :param prev_nc_code_id: 기존 nc_code의 its_id (제거 대상)
    :return: 성공 여부
    """
    main_workplan = data['project'].get("main_workplan")
    if not main_workplan:
        return False

    elements = main_workplan.get("its_elements", [])
    if not isinstance(elements, list):
        elements = [elements]

    def update_nc_code_list(target: dict) -> bool:
        nc_code = target.get("nc_code")
        if nc_code and isinstance(nc_code, dict):
            nc_code = [nc_code]
        elif not nc_code:
            nc_code = []
        # 기존 ID 제거
        nc_code = [item for item in nc_code if item.get("its_id") != prev_nc_code_id]
        # 새 ID 추가
        nc_code.append({"its_id": new_nc_code_id})
        target["nc_code"] = nc_code
        return True

    # its_elements 안의 workplan 수정
    for element in elements:
        if element.get("@xsi:type") == "workplan" and element.get("its_id") == workplan_id:
            return update_nc_code_list(element)
    # main_workplan 자체가 대상일 때도 허용
    if main_workplan.get("its_id") == workplan_id:
        return update_nc_code_list(main_workplan)
    return False

def replace_none_with_empty_list(obj):
    """
    dict 내부의 None 값을 모두 빈 리스트로 변환 (XML 파싱 결과의 일관성 보장).
    :param obj: 변환 대상 객체
    :return: 변환 결과
    """
    if isinstance(obj, dict):
        return {k: replace_none_with_empty_list(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_none_with_empty_list(item) for item in obj]
    elif obj is None:
        return []
    else:
        return obj

def save_xml_data(data: dict) -> str:
    """
    dict 데이터를 pretty xml string으로 직렬화.

    :param data: dict 데이터
    :return: XML 문자열(들여쓰기 포함)
    """
    import xmltodict, xml.dom.minidom
    xml_str = xmltodict.unparse(data, pretty=True)
    pretty_xml = xml.dom.minidom.parseString(xml_str).toprettyxml(indent="\t")
    return pretty_xml
