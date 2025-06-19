from motor.motor_asyncio import AsyncIOMotorCollection

class MachineLogRepository:
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection
    async def insert_log(self, log_doc):
        await self.collection.insert_one(log_doc)
