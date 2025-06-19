from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from src.schemas.project import ProjectSearchFilter

class ProjectRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self.project_collection = db["projects"]
        
    async def get_project_list(self, request: ProjectSearchFilter):
        match_stage = {}

        filters = []

        # name 부분 문자열 필터 (대소문자 구분 X)
        if request.name:
            filters.append({"name": {"$regex": request.name, "$options": "i"}})

        # project_id: ObjectId 일치 OR substring 검색
        if request.project_id:
            try:
                # 정확한 ObjectId라면 바로 사용
                filters.append({"_id": ObjectId(request.project_id)})
            except Exception:
                # ObjectId로 변환 안 되면 문자열로 부분 매칭
                filters.append({
                    "$expr": {
                        "$regexMatch": {
                            "input": { "$toString": "$_id" },
                            "regex": request.project_id,
                            "options": "i"
                        }
                    }
                })

        if filters:
            match_stage["$and"] = filters

        skip_count = max((request.page - 1), 0) * request.limit

        pipeline = [
            {"$match": match_stage} if match_stage else {},
            {"$skip": skip_count},
            {"$limit": request.limit}
        ]

        # 빈 dict {}는 pipeline에서 무시되므로 안전
        pipeline = [stage for stage in pipeline if stage]

        items = await self.project_collection.aggregate(pipeline).to_list(length=request.limit)
        return items

    async def get_project_by_id(self, project_id: str):
        return await self.project_collection.find_one({"_id": ObjectId(project_id)})
    
    async def update_project_data(self, project_id: str, updated_data: str):
        result = await self.project_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"data": updated_data}}
        )
        return result.modified_count > 0