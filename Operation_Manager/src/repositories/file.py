from io import BytesIO
from typing import Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId

class FileRepository:
    def __init__(self, grid_fs: AsyncIOMotorGridFSBucket):
        self.grid_fs = grid_fs
    
    async def insert_file(self, step_file_content: bytes, filename: str, metadata: Optional[dict] = None):
        file_id = await self.grid_fs.upload_from_stream(filename, step_file_content, metadata=metadata or {})
        return str(file_id)

    async def get_file(self, file_id: str):
        file_stream = await self.grid_fs.open_download_stream(ObjectId(file_id))
        return file_stream
    
    async def delete_file_by_id(self, file_id: str):
        await self.grid_fs.delete(ObjectId(file_id))
        return
    
    async def file_exists(self, file_id: str) -> bool:
        cursor = self.grid_fs.find({"_id": ObjectId(file_id)}, limit=1)
        docs = await cursor.to_list(length=1)
        return len(docs) > 0

    async def get_file_byteio(self, file_id: str) -> BytesIO:
        file_id = ObjectId(file_id)
        grid_out = await self.grid_fs.open_download_stream(file_id)
        file_bytes = await grid_out.read()
        return BytesIO(file_bytes)
    
    async def get_file_byteio_and_name(self, file_id: str) -> Tuple[BytesIO, str]:
        file_id = ObjectId(file_id)
        grid_out = await self.grid_fs.open_download_stream(file_id)
        file_bytes = await grid_out.read()
        filename = grid_out.filename
        return BytesIO(file_bytes), filename

