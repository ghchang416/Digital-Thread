from typing import List
from src.schemas.project import ProjectCreateResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

class ProjectRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.project_collection = db["projects"]

    async def insert_project(self, xml_string: str) -> ProjectCreateResponse:
        project_data = {"data": xml_string}
        result = await self.project_collection.insert_one(project_data)
        return ProjectCreateResponse(project_id=str(result.inserted_id))

    async def get_project_list(self) -> List[dict]:
        cursor = self.project_collection.find({})
        projects = await cursor.to_list(length=None)
        return projects
    
    async def delete_project_by_id(self, project_id: str) -> bool:
        result = await self.project_collection.delete_one({"_id": ObjectId(project_id)})
        return result.deleted_count > 0
    
    async def get_project_by_id(self, project_id: str):
        return await self.project_collection.find_one({"_id": ObjectId(project_id)})

    async def add_file_to_project(self, project_id: str, file_id: str, file_type: str):
        update_query = {}
        update_query["$push"] = {f"{file_type}_id": file_id}
        
        result = await self.project_collection.update_one(
            {"_id": ObjectId(project_id)},
            update_query
        )        
        return result.modified_count > 0

    async def add_dict_to_project(self, project_id: str, file_dict: dict):
        update_query = {"$set": file_dict}
        result = await self.project_collection.update_one(
            {"_id": ObjectId(project_id)},
            update_query
        )        
        return result.modified_count > 0

    async def update_project_data(self, project_id: str, updated_data: str):
        result = await self.project_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"data": updated_data}}
        )
        return result.modified_count > 0