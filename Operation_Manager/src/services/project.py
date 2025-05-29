from io import BytesIO
import xmltodict
import xml.etree.ElementTree as ET
from typing import List, Dict
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket
from src.utils.exceptions import CustomException, ExceptionEnum
from src.schemas.project import ProjectOut, ProjectSearchFilter, WorkplanNCResponse, WorkplanNC, NCCodeResponse
from src.entities.file import FileRepository
from src.entities.project import ProjectRepository
import xml.dom.minidom

class ProjectService:
    def __init__(self, collection: AsyncIOMotorCollection, grid_fs: AsyncIOMotorGridFSBucket):
        self.project_repository = ProjectRepository(collection)
        self.file_repository = FileRepository(grid_fs)
    
    async def get_project_list(self, filter: ProjectSearchFilter):
        projects = await self.project_repository.get_project_list(filter)
        projects = [
            ProjectOut(
                id=str(project["_id"]),
                name=self._extract_its_id(project.get("data", ""))
            )
            for project in projects
        ]
        
        return {
            "items": projects,
            "total_count": len(projects)
        }

    async def extract_workplan_and_nc(self, project_id: str) -> WorkplanNCResponse:
        project = await self.project_repository.get_project_by_id(project_id)
        xml_string = project.get("data", "")
        try:
            data = xmltodict.parse(xml_string)
            main_workplan = data["project"].get("main_workplan")
            results = []

            # Case 1: main_workplan 자체 처리
            if main_workplan.get("its_id"):
                results.append(WorkplanNC(
                    workplan_id=main_workplan["its_id"],
                    nc_code_id=self._extract_nc_list(main_workplan)
                ))

            # Case 2: its_elements 안에 포함된 workplan들
            its_elements = main_workplan.get("its_elements")
            if its_elements:
                if not isinstance(its_elements, list):
                    its_elements = [its_elements]
                for element in its_elements:
                    if (
                        isinstance(element, dict) and
                        element.get("@xsi:type") == "workplan" and
                        element.get("its_id")
                    ):
                        results.append(WorkplanNC(
                            workplan_id=main_workplan["its_id"],
                            nc_code_id=self._extract_nc_list(element)
                        ))
            return WorkplanNCResponse(results=results)
        except Exception as e:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT, str(e))
        

    async def get_nc_code(self, project_id: str, workplan_id: str, nc_code_id: str) -> NCCodeResponse:
        """
        특정 프로젝트와 워크플랜에 속한 NC 코드의 실제 파일 내용 조회
        """
        # 검증: 해당 프로젝트에 이 nc_code_id가 실제로 포함되어 있는지 확인
        project = await self.project_repository.get_project_by_id(project_id)
        if not project:
            raise CustomException(ExceptionEnum.PROJECT_NOT_FOUND)

        xml_string = project.get("data", "")
        if not self._verify_nc_code_in_workplan(xml_string, workplan_id, nc_code_id):
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)

        # GridFS에서 파일 가져오기
        try:
            byte_io = await self.file_repository.get_file_byteio(nc_code_id)
            content = byte_io.read().decode("utf-8")  # 👉 텍스트로 변환
            return NCCodeResponse(content=content)
        except Exception:
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)

    async def update_nc_code(
        self, project_id: str, workplan_id: str, nc_code_id: str, new_nc_file: BytesIO) -> dict:
        """
        기존 NC 코드를 삭제하고 새 파일로 업데이트하며 XML의 its_id도 갱신
        """
        # 프로젝트 불러오기
        project = await self.project_repository.get_project_by_id(project_id)
        if not project:
            raise CustomException(ExceptionEnum.PROJECT_NOT_FOUND)

        xml_string = project.get("data", "")
        if not xml_string:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

        await self.file_repository.delete_file_by_id(nc_code_id)

        # 새 NC 파일 업로드
        new_file_id = await self.file_repository.insert_file(new_nc_file.read(), f"{nc_code_id}.nc")

        # XML 내 해당 workplan의 nc_code its_id 갱신
        try:
            data_dict = xmltodict.parse(xml_string)
            updated = self._update_nc_code_id_in_workplan(data_dict, workplan_id, new_file_id)
            if not updated:
                raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

            new_xml_string = xmltodict.unparse(data_dict, pretty=True)

        except Exception:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

        # MongoDB 업데이트
        await self.project_repository.update_project_data(project_id, new_xml_string)

        return
    
    def _verify_nc_code_in_workplan(self, xml_string: str, workplan_id: str, nc_code_id: str) -> bool:
        """
        해당 workplan 내에 주어진 nc_code_id가 존재하는지 확인
        """
        try:
            data_dict = xmltodict.parse(xml_string)
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

            # case: main_workplan 자체가 해당 workplan일 경우
            if main_workplan.get("its_id") == workplan_id:
                nc_codes = main_workplan.get("nc_code", [])
                if isinstance(nc_codes, dict):
                    nc_codes = [nc_codes]
                return any(nc.get("its_id") == nc_code_id for nc in nc_codes)

            return False
        except Exception:
            return False

    def _update_nc_code_id_in_workplan(self, data: dict, workplan_id: str, new_nc_code_id: str) -> bool:
        """
        XML dict 구조에서 해당 workplan의 nc_code 리스트에 새로운 its_id를 append
        """
        main_workplan = data['project'].get("main_workplan")
        if not main_workplan:
            return False

        elements = main_workplan.get("its_elements", [])
        if not isinstance(elements, list):
            elements = [elements]

        for element in elements:
            if element.get("@xsi:type") == "workplan" and element.get("its_id") == workplan_id:
                if not element.get("nc_code"):
                    element["nc_code"] = []
                elif isinstance(element["nc_code"], dict):
                    element["nc_code"] = [element["nc_code"]]

                element["nc_code"].append({"its_id": new_nc_code_id})
                return True

        if main_workplan.get("its_id") == workplan_id:
            if not main_workplan.get("nc_code"):
                main_workplan["nc_code"] = []
            elif isinstance(main_workplan["nc_code"], dict):
                main_workplan["nc_code"] = [main_workplan["nc_code"]]

            main_workplan["nc_code"].append({"its_id": new_nc_code_id})
            return True

        return False
        
    def _extract_its_id(self, xml_string: str) -> str:
        try:
            root = ET.fromstring(xml_string)
            return root.attrib.get("its_id", "unknown")
        except Exception:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

    def _extract_nc_list(self, workplan: dict) -> List[str]:
        nc = workplan.get("nc_code", [])
        if isinstance(nc, dict):
            nc = [nc]
        return [item.get("its_id") for item in nc if isinstance(item, dict)]