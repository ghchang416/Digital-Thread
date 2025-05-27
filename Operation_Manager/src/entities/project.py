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

        cursor = self.project_collection.find(query).skip(request.page-1).limit(request.limit)
        items = await cursor.to_list(length=request.limit)

        return items