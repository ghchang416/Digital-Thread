import json
from typing import Optional
from fastapi import UploadFile
import xmltodict
import xml.etree.ElementTree as ET
from motor.motor_asyncio import AsyncIOMotorCollection 
from src.schemas.project import ProjectListResponse
from src.entities.model import Project
from src.utils.exceptions import CustomException, ExceptionEnum
from src.utils.xml_parser import create_feature_xml, ensure_empty_lists, update_xml_from_dataclass, parser, remove_empty_lists, serializer
import logging
from src.entities.project import ProjectRepository
import xml.dom.minidom

class ProjectService:
    """
    프로젝트 생성, 조회, 삭제, 파일/캠 데이터 등록, XML 핸들링 등 
    프로젝트 업무 전반을 담당하는 서비스 클래스.
    """
    def __init__(self, collection: AsyncIOMotorCollection):
        # MongoDB collection 주입, 실제 작업은 ProjectRepository에 위임
        self.repository = ProjectRepository(collection)

    async def create_project(self, xml_string: str):
        """
        신규 프로젝트 생성.
        XML을 dict로 파싱, its_id 추출 후 저장. 
        """
        xml_dict = self.xml_to_dict(xml_string)
        its_id = xml_dict["project"]["its_id"]
        xml_string = self.save_xml_data(xml_dict)
        project_data = await self.repository.insert_project(xml_string, its_id)
        if not project_data:
            raise CustomException(ExceptionEnum.PROJECT_CREATION_FAILED)
        return project_data
    
    async def get_project_list(self) -> ProjectListResponse:
        """
        전체 프로젝트 목록 조회 (project_id만 반환).
        """
        projects = await self.repository.get_project_list()
        project_ids = [str(project["_id"]) for project in projects]
        return ProjectListResponse(project_id=project_ids)
    
    async def get_project_by_id(self, xml_string: str):
        """
        프로젝트 ID로 프로젝트 조회.
        """
        project = await self.repository.get_project_by_id(xml_string)
        if not project:
            raise CustomException(ExceptionEnum.PROJECT_NOT_FOUND)
        return project
    
    async def delete_project_by_id(self, project_id: str) -> None:
        """
        프로젝트 삭제. 실패 시 예외 발생.
        """
        deleted = await self.repository.delete_project_by_id(project_id)
        if not deleted:
            raise CustomException(ExceptionEnum.PROJECT_DELETE_FAILED)
        return

    async def file_upload(self, project_id: str, file_id: str, file_type: str):
        """
        프로젝트에 파일(ObjectId) 연결. file_type에 따라 필드 결정.
        """
        status = await self.repository.add_file_to_project(project_id, file_id, file_type)
        if not status:
            raise CustomException(ExceptionEnum.STP_UPLOAD_FAILED)
        return

    async def _insert_to_workplan_element(
        self,
        data: dict,
        workplan_id: str,
        type_key: str,
        value_dict: dict
    ) -> bool:
        """
        workplan 요소(its_elements, 혹은 main_workplan 자체)에 
        nc_code, vm, tdms 등 삽입.
        value_dict: 삽입할 데이터 dict
        """
        main_workplan = data['project'].get("main_workplan")
        if not main_workplan:
            return False

        its_elements = main_workplan.get("its_elements")

        # case 1: its_elements 리스트 탐색
        if its_elements:
            if not isinstance(its_elements, list):
                its_elements = [its_elements]

            for element in its_elements:
                if element.get("@xsi:type") == "workplan" and element.get("its_id") == workplan_id:
                    if not element.get(type_key):
                        element[type_key] = []
                    elif isinstance(element[type_key], dict):
                        element[type_key] = [element[type_key]]

                    element[type_key].append(value_dict)
                    return True

        # case 2: main_workplan 자체가 workplan일 경우
        if main_workplan.get("its_id") == workplan_id:
            if not main_workplan.get(type_key):
                main_workplan[type_key] = []
            elif isinstance(main_workplan[type_key], dict):
                main_workplan[type_key] = [main_workplan[type_key]]

            main_workplan[type_key].append(value_dict)
            return True

        return False
    
    async def nc_upload(self, project: dict, workplan_id: str, file_id: str):
        """
        NC 코드 파일 업로드 및 프로젝트 XML 데이터에 삽입.
        """
        data = xmltodict.parse(project['data'])

        found = await self._insert_to_workplan_element(
            data, workplan_id, "nc_code", {"its_id": file_id}
        )
        if not found:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        updated = self.save_xml_data(data)
        await self.repository.update_project_data(project['_id'], updated)

    async def vm_upload(self, project: dict, workplan_id: str, file_id: str):
        """
        VM 파일 업로드 및 프로젝트 XML 데이터에 삽입.
        """
        data = xmltodict.parse(project['data'])

        found = await self._insert_to_workplan_element(
            data, workplan_id, "vm", {"its_id": file_id}
        )

        if not found:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        updated = self.save_xml_data(data)
        await self.repository.update_project_data(project['_id'], updated)

    async def tdms_upload(self, project: dict, workplan_id: str, file_id: str, tdms_path: str):
        """
        TDMS 파일 업로드 및 프로젝트 XML 데이터에 삽입.
        """
        data = xmltodict.parse(project['data'])

        found = await self._insert_to_workplan_element(
            data, workplan_id, "tdms", {"raw": tdms_path, "ext": file_id}
        )

        if not found:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        updated = self.save_xml_data(data)
        await self.repository.update_project_data(project['_id'], updated)

    async def stp_upload(self, project_id: str, file_id: dict):
        """
        프로젝트에 step, stl 등 여러 파일 ObjectId(dict)를 한번에 추가.
        """
        status = await self.repository.add_dict_to_project(project_id, file_id)
        if not status:
            raise CustomException(ExceptionEnum.STP_UPLOAD_FAILED)
        return

    async def add_cam_to_proejct(self, project: dict, cam_type: str, cam_json_file: UploadFile, mapping_json_file: UploadFile):
        """
        CAM (NX/파워밀) 데이터 업로드 및 XML 변환, 프로젝트에 추가.
        """
        json_data = (await cam_json_file.read()).decode("utf-8-sig")
        mapping_data = (await mapping_json_file.read()).decode("utf-8-sig")
        data = self.xml_to_dict(project['data'])
        
        updated_project = await self.process_cam_upload(data, cam_type, json_data, mapping_data)        
        update_data = self.save_xml_data(updated_project)
        success = await self.repository.update_project_data(project["_id"], update_data)
        if not success:
            raise CustomException(ExceptionEnum.PROJECT_UPLOAD_FAILED)            
        return

    async def process_cam_upload(self, project: dict, cam_type: str, json_data: str, mapping_data: str):
        """
        CAM 데이터 및 매핑 데이터 파싱 후 XML로 변환하여 its_elements에 삽입.
        """
        print(project)
        parsed_data = json.loads(json_data)
        mapping_data = json.loads(mapping_data)

        if "main_workplan" not in project["project"]:
            project["project"]["main_workplan"] = {"its_elements": []}
        elif "its_elements" not in project["project"]["main_workplan"]:
            project["project"]["main_workplan"]["its_elements"] = []
        
        if not isinstance(project["project"]["main_workplan"]["its_elements"], list):
            project["project"]["main_workplan"]["its_elements"] = [project["project"]["main_workplan"]["its_elements"]]

        if cam_type == "nx":
            for data in parsed_data['values']:
                nx_xml = create_feature_xml(data, mapping_data)
                nx_data_parsed = xmltodict.parse(nx_xml)
                project["project"]["main_workplan"]["its_elements"].append(nx_data_parsed["its_elements"])
        else:
            if isinstance(parsed_data, dict):
                parsed_data = [parsed_data]
            for data in parsed_data:
                powermill_xml = create_feature_xml(data, mapping_data)
                powermill_data_parsed = xmltodict.parse(powermill_xml)
                project["project"]["main_workplan"]["its_elements"].append(powermill_data_parsed["its_elements"])

        return project

    def xml_to_dict(self, project_xml: str):
        """프로젝트 XML을 dict로 변환."""
        project_dict = xmltodict.parse(project_xml)
        return project_dict
    
    def save_xml_data(self, data: dict):
        """
        dict → XML 변환 및 데이터클래스 기반 보정.
        pretty XML string 반환.
        """
        data = xmltodict.unparse(data, pretty=True)
        data_class = parser.from_string(data, Project)
        xml_string = update_xml_from_dataclass(data, data_class)
        pretty_xml = xml.dom.minidom.parseString(xml_string).toprettyxml(indent="\t")
        return pretty_xml
    
    def get_inner_data(self, project: str, path: str):
        """
        XML 내에서 특정 경로(path) 요소만 추출하여 XML로 반환.
        """
        path = path.split("/")
        parent_element = path[-1]
        data = self.get_nested_attribute(data=project, attributes=path)
        if isinstance(data, list):
            data = {path[-1]: item for item in data}
            parent_element = path[-2]
        if path[-1].isdigit():
            parent_element = path[-2]            
        data = xmltodict.unparse({parent_element: data}, pretty=True, attr_prefix="@")
        return data
    
    def get_nested_attribute(self, data, attributes):
        """
        dict/list 구조에서 attribute 경로 따라 하위 요소 접근.
        """
        for attr in attributes:
            if isinstance(data, dict):
                data = data.get(attr, None)
            elif isinstance(data, list) and attr.isdigit():
                data = data[int(attr)] if len(data) > int(attr) else None
            else:
                return None
        return data
    
    def valid_file_id(self, data: dict, workplan_id: str, file_id: str, file_type: str):
        """
        workplan에 특정 파일(file_id)이 존재하는지 확인. 없으면 예외.
        """
        xml_data = self.xml_to_dict(data['data'])
        project = xml_data.get("project")
        if not project:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        main_workplan: dict = project.get("main_workplan")
        if not main_workplan:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        target_workplan = self._find_target_workplan(main_workplan, workplan_id)
        if not target_workplan:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        if not self._check_file_exists(target_workplan, file_type, file_id):
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)

        return

    def _find_target_workplan(self, main_workplan: dict, workplan_id: str) -> Optional[dict]:
        """
        main_workplan 내에서 its_id로 해당 workplan dict 반환.
        """
        its_elements = main_workplan.get("its_elements")
        if its_elements:
            if not isinstance(its_elements, list):
                its_elements = [its_elements]

            for element in its_elements:
                if element.get("@xsi:type") == "workplan" and element.get("its_id") == workplan_id:
                    return element
        elif main_workplan.get("its_id") == workplan_id:
            return main_workplan

        return None
    
    def _check_file_exists(self, workplan: dict, file_type: str, file_id: str) -> bool:
        """
        workplan dict에서 해당 file_type(list) 중 file_id 포함 여부 확인.
        """
        file_list = workplan.get(file_type)

        if not file_list:
            return False

        if isinstance(file_list, dict):
            file_list = [file_list]

        if file_type == "tdms":
            return any(tdms.get("ext") == file_id for tdms in file_list)

        return any(item.get("its_id") == file_id for item in file_list)

    def get_tdms_list(self, data: str, workplan_id: str) -> list[str]:
        xml_data = self.xml_to_dict(data['data'])
        project = xml_data.get("project")
        if not project:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        main_workplan: dict = project.get("main_workplan")
        if not main_workplan:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)
        target_workplan = self._find_target_workplan(main_workplan, workplan_id)
        if not target_workplan:
            raise CustomException(ExceptionEnum.INVALID_ATTRIBUTE)

        tdms_list = target_workplan.get("tdms") or []
        if isinstance(tdms_list, dict):
            tdms_list = [tdms_list]

        return [tdms.get("raw") for tdms in tdms_list if tdms.get("raw")]

        
        