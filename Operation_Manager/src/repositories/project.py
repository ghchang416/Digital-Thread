from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from src.schemas.project import ProjectSearchFilter

class ProjectRepository:
    """
    MongoDB projects 컬렉션을 활용한 프로젝트 관련 데이터 관리 리포지토리.
    """
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        :param db: Motor 기반 MongoDB 데이터베이스 핸들
        """
        self.project_collection = db["projects"]

    async def get_project_list(self, request: ProjectSearchFilter):
        """
        프로젝트 리스트를 검색 조건(name/project_id/페이징) 기반으로 조회.
        :param request: ProjectSearchFilter(검색 조건 포함)
        :return: 프로젝트 문서 리스트
        """
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
                # ObjectId 변환 실패 시 부분 문자열 매칭
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

        # 빈 dict {}는 pipeline에서 무시됨
        pipeline = [stage for stage in pipeline if stage]

        items = await self.project_collection.aggregate(pipeline).to_list(length=request.limit)
        return items

    async def get_project_by_id(self, project_id: str):
        """
        project_id(ObjectId)로 단일 프로젝트 조회.
        :param project_id: 프로젝트 id (hex string)
        :return: 프로젝트 문서(dict)
        """
        return await self.project_collection.find_one({"_id": ObjectId(project_id)})

    async def update_project_data(self, project_id: str, updated_data: str):
        """
        프로젝트의 data 필드를 수정(업데이트).
        :param project_id: 프로젝트 id (hex string)
        :param updated_data: 새 XML 등 데이터(str)
        :return: True(성공) / False(수정안됨)
        """
        result = await self.project_collection.update_one(
            {"_id": ObjectId(project_id)},
            {"$set": {"data": updated_data}}
        )
        return result.modified_count > 0
