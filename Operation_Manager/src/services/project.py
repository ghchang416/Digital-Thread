import xmltodict
import xml.etree.ElementTree as ET
from motor.motor_asyncio import AsyncIOMotorCollection 
from src.utils.exceptions import CustomException, ExceptionEnum
from src.schemas.project import ProjectOut, ProjectSearchFilter
from src.entities.project import ProjectRepository
import xml.dom.minidom

class ProjectService:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.repository = ProjectRepository(collection)
    
    async def get_project_list(self, filter: ProjectSearchFilter):
        projects = await self.repository.get_project_list(filter)
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
    
    def _extract_its_id(self, xml_string: str) -> str:
        try:
            root = ET.fromstring(xml_string)
            return root.attrib.get("its_id", "unknown")
        except Exception:
            raise CustomException(ExceptionEnum.INVALID_XML_FORMAT)