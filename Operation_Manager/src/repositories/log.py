from motor.motor_asyncio import AsyncIOMotorCollection
from src.utils.exceptions import CustomException, ExceptionEnum

class MachineLogRepository:
    """
    MongoDB 컬렉션 기반 가공 로그 관리 리포지토리
    """
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def insert_log(self, log_doc):
        """
        새 가공 로그 문서 insert (오류 발생 시 CustomException 반환)
        """
        try:
            await self.collection.insert_one(log_doc)
        except Exception as e:
            raise CustomException(ExceptionEnum.DATABASE_ERROR, detail=str(e))

    async def get_logs_by_project_id(self, project_id: str):
        """
        특정 프로젝트 ID에 대한 모든 가공 로그 조회 (없으면 예외)
        """
        try:
            cursor = self.collection.find({"project_id": project_id})
            logs = await cursor.to_list(length=None)
            return logs
        except CustomException:
            raise
        except Exception as e:
            raise CustomException(ExceptionEnum.DATABASE_ERROR, detail=str(e))
