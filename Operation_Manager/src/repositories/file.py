from io import BytesIO
from typing import Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId

class FileRepository:
    """
    MongoDB GridFS를 통한 대용량 파일(바이너리) 저장/조회/삭제/존재확인 등 기능 제공.
    """
    def __init__(self, grid_fs: AsyncIOMotorGridFSBucket):
        self.grid_fs = grid_fs

    async def insert_file(self, step_file_content: bytes, filename: str, metadata: Optional[dict] = None):
        """
        새 파일을 GridFS에 저장하고, 파일 id(ObjectId)를 반환합니다.
        """
        file_id = await self.grid_fs.upload_from_stream(filename, step_file_content, metadata=metadata or {})
        return str(file_id)

    async def get_file(self, file_id: str):
        """
        파일 id(ObjectId)로 다운로드 스트림 핸들 반환.
        """
        file_stream = await self.grid_fs.open_download_stream(ObjectId(file_id))
        return file_stream

    async def delete_file_by_id(self, file_id: str):
        """
        파일 id로 GridFS에서 파일 삭제.
        """
        await self.grid_fs.delete(ObjectId(file_id))
        return

    async def file_exists(self, file_id: str) -> bool:
        """
        파일 id로 존재 여부 확인.
        """
        cursor = self.grid_fs.find({"_id": ObjectId(file_id)}, limit=1)
        docs = await cursor.to_list(length=1)
        return len(docs) > 0

    async def get_file_byteio(self, file_id: str) -> BytesIO:
        """
        파일 id로 GridFS에서 전체 바이트 스트림(BytesIO) 반환.
        """
        file_id = ObjectId(file_id)
        grid_out = await self.grid_fs.open_download_stream(file_id)
        file_bytes = await grid_out.read()
        return BytesIO(file_bytes)

    async def get_file_byteio_and_name(self, file_id: str) -> Tuple[BytesIO, str]:
        """
        파일 id로 (BytesIO, 파일명) 튜플 반환.
        """
        file_id = ObjectId(file_id)
        grid_out = await self.grid_fs.open_download_stream(file_id)
        file_bytes = await grid_out.read()
        filename = grid_out.filename
        return BytesIO(file_bytes), filename
