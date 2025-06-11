from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from src.schemas.project import ProjectSearchFilter

class ProjectRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.project_collection = db["projects"]
        
    async def get_project_list(self, request: ProjectSearchFilter):
        query = {}

        if request.name:
            query["name"] = {"$regex": request.name, "$options": "i"}
        if request.project_id:
            try:
                query["_id"] = ObjectId(request.project_id)
            except Exception:
                return []  # 잘못된 ID 형식

        skip_count = max((request.page - 1), 0) * request.limit
        cursor = self.project_collection.find(query).skip(skip_count).limit(request.limit)
        items = await cursor.to_list(length=request.limit)

        return items

    async def get_project_by_id(self, project_id: str):
        return await self.project_collection.find_one({"_id": ObjectId(project_id)})
    
    async def update_project_data(self, project_id: str, updated_data: str):
        result = await self.project_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"data": updated_data}}
        )
        return result.modified_count > 0