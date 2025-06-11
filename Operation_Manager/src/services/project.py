import io
import chardet
from io import BytesIO
import xmltodict
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorGridFSBucket
from src.utils.exceptions import CustomException, ExceptionEnum
from src.schemas.project import ProductLog, ProductLogResponse, ProjectOut, ProjectSearchFilter, WorkplanNCResponse, WorkplanNC, NCCodeResponse
from src.entities.file import FileRepository
from src.services.redis import RedisJobTracker
from src.entities.project import ProjectRepository
from src.entities.model import Project
from src.utils.xml_parser import create_feature_xml, ensure_empty_lists, update_xml_from_dataclass, parser, remove_empty_lists, serializer
import xml.dom.minidom

class ProjectService:
    def __init__(self, collection: AsyncIOMotorCollection, grid_fs: AsyncIOMotorGridFSBucket, product_log_collection: AsyncIOMotorCollection):
        self.project_repository = ProjectRepository(collection)
        self.file_repository = FileRepository(grid_fs)
        self.product_log_collection = product_log_collection  
    
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
            data = self._xml_to_dict(xml_string)
            main_workplan = data["project"].get("main_workplan")
            results = []

            # Case 1: main_workplan 자체 처리
            if main_workplan.get("its_id"):
                results.append(await self._build_workplan_nc(main_workplan))

            # Case 2: its_elements 내부 workplan 처리
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
                        results.append(await self._build_workplan_nc(element))

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
        data = self._xml_to_dict(xml_string)
        if not self._verify_nc_code_in_workplan(data, workplan_id, nc_code_id):
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)
        try:
            byte_io = await self.file_repository.get_file_byteio(nc_code_id)
            byte_io.seek(0)
            content_bytes = byte_io.read()

            encoding = chardet.detect(content_bytes)["encoding"] or "utf-8"
            content = content_bytes.decode(encoding)

            return NCCodeResponse(content=content)

        except Exception as e:
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)


    async def update_nc_code(self, project_id: str, workplan_id: str, nc_code_id: str, new_nc_content: str) -> dict:
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

        # 기존 NC 파일 삭제
        await self.file_repository.delete_file_by_id(nc_code_id)

        # 새 NC 파일 업로드 (문자열 → BytesIO로 인코딩)
        new_file_io = io.BytesIO(new_nc_content.encode("utf-8"))
        new_file_id = await self.file_repository.insert_file(new_file_io, f"{nc_code_id}.nc")

        # XML 내 해당 workplan의 nc_code its_id 갱신
        try:
            data_dict = self._xml_to_dict(xml_string)
            updated = self._update_nc_code_id_in_workplan(data_dict, workplan_id, new_file_id, nc_code_id)
            if not updated:
                raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

            new_xml_string = self._save_xml_data(data_dict)
        except Exception:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

        # MongoDB에 XML 갱신
        await self.project_repository.update_project_data(project_id, new_xml_string)

        return

    async def get_product_logs_by_project_id(self, project_id: str) -> ProductLogResponse:
        try:
            logs_cursor = self.product_log_collection.find({"project_id": project_id})
            logs = await logs_cursor.to_list(length=None)
            return ProductLogResponse(
                logs=[ProductLog(**log) for log in logs]
            )
        except Exception:
            raise CustomException(ExceptionEnum.PROJECT_NOT_FOUND)

    def get_machine_status_info(self, project_id: str):
        redis_tracker = RedisJobTracker()
        pattern = f"status:{project_id}:*"
        keys = redis_tracker.redis_client.keys(pattern)

        statuses = {}
        for key in keys:
            fname = key.split(":")[-1]
            status = redis_tracker.redis_client.hget(key, "status") or "알 수 없음"
            machine_id = redis_tracker.redis_client.hget(key, "machine_id") or "알 수 없음"

            statuses[fname] = {
                "status": status,
                "machine_id": machine_id
            }

        return {"statuses": statuses}


    async def _build_workplan_nc(self, element: dict) -> WorkplanNC:
        nc_code_id = self._extract_nc_id(element)
        filename: Optional[str] = None
        try:
            _, filename = await self.file_repository.get_file_byteio_and_name(nc_code_id)
        except Exception:
            pass

        return WorkplanNC(
            workplan_id=element["its_id"],
            nc_code_id=nc_code_id,
            filename=filename
        )
    
    def _verify_nc_code_in_workplan(self, data_dict: str, workplan_id: str, nc_code_id: str) -> bool:
        """
        해당 workplan 내에 주어진 nc_code_id가 존재하는지 확인
        """
        main_workplan = data_dict['project'].get("main_workplan")
        if not main_workplan:
            return False

        elements = main_workplan.get("its_elements", [])
        if not isinstance(elements, list):
            elements = [elements]

        print(elements)
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


    def _update_nc_code_id_in_workplan(
        self,
        data: dict,
        workplan_id: str,
        new_nc_code_id: str,
        prev_nc_code_id: str
    ) -> bool:
        """
        XML dict 구조에서 해당 workplan의 nc_code 리스트에서 prev_nc_code_id 제거 후 new_nc_code_id 추가
        """
        main_workplan = data['project'].get("main_workplan")
        if not main_workplan:
            return False

        elements = main_workplan.get("its_elements", [])
        if not isinstance(elements, list):
            elements = [elements]

        def update_nc_code_list(target: dict) -> bool:
            nc_code = target.get("nc_code")

            # dict → list로 변환
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

        for element in elements:
            if element.get("@xsi:type") == "workplan" and element.get("its_id") == workplan_id:
                return update_nc_code_list(element)

        if main_workplan.get("its_id") == workplan_id:
            return update_nc_code_list(main_workplan)

        return False

        
    def _extract_its_id(self, xml_string: str) -> str:
        data = self._xml_to_dict(xml_string)
        try:
            return data["project"]["its_id"]
        except (KeyError, TypeError):
            return "unknown"


    def _extract_nc_id(self, workplan: dict) -> str:
        nc_code = workplan.get("nc_code", {})
        if isinstance(nc_code, dict):
            return nc_code.get("its_id", "unknown")
        return None
    
    def _xml_to_dict(self, project_xml: str):
        project_dict = xmltodict.parse(project_xml)
        return self._replace_none_with_empty_list(project_dict)

    def _replace_none_with_empty_list(self, obj):
        if isinstance(obj, dict):
            return {k: self._replace_none_with_empty_list(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._replace_none_with_empty_list(item) for item in obj]
        elif obj is None:
            return []
        else:
            return obj

    def _save_xml_data(self, data: dict):
        data = xmltodict.unparse(data, pretty=True)
        data_class = parser.from_string(data, Project)
        xml_string = update_xml_from_dataclass(data, data_class)
        pretty_xml = xml.dom.minidom.parseString(xml_string).toprettyxml(indent="\t")
        return pretty_xml