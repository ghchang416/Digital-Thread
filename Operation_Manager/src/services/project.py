# src/services/project_service.py

from src.repositories import ProjectRepository, FileRepository, MachineLogRepository, RedisRepository
from src.schemas.project import ProjectOut, ProjectSearchFilter, WorkplanNCResponse, WorkplanNC, NCCodeResponse, ProductLog, ProductLogResponse
from src.utils.xml_utils import (
    extract_its_id,
    xml_to_dict,
    extract_workplans_with_nc,
    extract_nc_id,
    verify_nc_code_in_workplan,
    update_nc_code_id_in_workplan,
    save_xml_data,
)
from src.utils.exceptions import CustomException, ExceptionEnum
import chardet
import io

class ProjectService:
    def __init__(self, project_repo: ProjectRepository, file_repo: FileRepository, log_repo: MachineLogRepository, redis_repo: RedisRepository):
        self.project_repo = project_repo
        self.file_repo = file_repo
        self.log_repo = log_repo
        self.redis_repo = redis_repo

    async def get_project_list(self, filter: ProjectSearchFilter):
        projects = await self.project_repo.get_project_list(filter)
        project_outs = [
            ProjectOut(
                id=str(p["_id"]),
                name=extract_its_id(p.get("data", "")),
            )
            for p in projects
        ]
        return {
            "items": project_outs,
            "total_count": len(project_outs)
        }

    async def extract_workplan_and_nc(self, project_id: str) -> WorkplanNCResponse:
        project = await self.project_repo.get_project_by_id(project_id)
        xml_string = project.get("data", "")
        data = xml_to_dict(xml_string)
        workplans = extract_workplans_with_nc(data)
        results = []
        for element in workplans:
            nc_code_id = extract_nc_id(element)
            filename = None
            try:
                _, filename = await self.file_repo.get_file_byteio_and_name(nc_code_id)
            except Exception:
                pass
            results.append(WorkplanNC(
                workplan_id=element["its_id"],
                nc_code_id=nc_code_id,
                filename=filename,
            ))
        return WorkplanNCResponse(results=results)

    async def get_nc_code(self, project_id: str, workplan_id: str, nc_code_id: str) -> NCCodeResponse:
        project = await self.project_repo.get_project_by_id(project_id)
        xml_string = project.get("data", "")
        data = xml_to_dict(xml_string)
        if not verify_nc_code_in_workplan(data, workplan_id, nc_code_id):
            raise CustomException(ExceptionEnum.NO_DATA_FOUND)
        byte_io = await self.file_repo.get_file_byteio(nc_code_id)
        byte_io.seek(0)
        content_bytes = byte_io.read()
        encoding = chardet.detect(content_bytes)["encoding"] or "utf-8"
        content = content_bytes.decode(encoding)
        return NCCodeResponse(content=content)

    async def update_nc_code(self, project_id: str, workplan_id: str, nc_code_id: str, new_nc_content: str):
        _, filename = await self.file_repo.get_file_byteio_and_name(nc_code_id)
        project = await self.project_repo.get_project_by_id(project_id)
        xml_string = project.get("data", "")
        if not xml_string:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)

        # 기존 NC 파일 삭제, 새로 업로드
        await self.file_repo.delete_file_by_id(nc_code_id)
        new_file_io = io.BytesIO(new_nc_content.encode("utf-8"))
        new_file_id = await self.file_repo.insert_file(new_file_io, filename)
        data_dict = xml_to_dict(xml_string)
        updated = update_nc_code_id_in_workplan(data_dict, workplan_id, new_file_id, nc_code_id)
        if not updated:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)
        new_xml_string = save_xml_data(data_dict)
        await self.project_repo.update_project_data(project_id, new_xml_string)
        return

    async def get_product_logs_by_project_id(self, project_id: str) -> ProductLogResponse:
        logs = await self.log_repo.get_logs_by_project_id(project_id)
        return ProductLogResponse(logs=[ProductLog(**log) for log in logs])

    def get_machine_status_info(self, project_id: str):
        pattern = f"status:{project_id}:*"
        keys = self.redis_repo.redis_client.keys(pattern)
        statuses = {}
        for key in keys:
            fname = key.split(":")[-1]
            status = self.redis_repo.redis_client.hget(key, "status") or "알 수 없음"
            machine_id = self.redis_repo.redis_client.hget(key, "machine_id") or "알 수 없음"
            statuses[fname] = {"status": status, "machine_id": machine_id}
        return {"statuses": statuses}
