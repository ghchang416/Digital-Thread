# src/services/vm_file.py
from __future__ import annotations
import os
import asyncio
from typing import Optional, Literal, Dict, Any, AsyncIterator
from bson import ObjectId

from src.dao.vm_file import VmFileDAO, Kind
from src.dao.files import GridFSFileStore


class VmFileService:
    def __init__(self, dao: VmFileDAO, filestore: GridFSFileStore):
        self.dao = dao
        self.filestore = filestore

    async def create_from_path(
        self,
        *,
        vm_project_id: ObjectId,
        kind: Kind,
        file_path: str,
        original_name: str,
        content_type: str,
        meta: Optional[Dict[str, Any]] = None,
        small_file_threshold: int = 64 * 1024 * 1024,  # 64MB
    ) -> ObjectId:
        """
        - file_path 내용을 GridFS로 업로드하고
        - vm_file 레코드 한 건을 생성하여 _id 반환
        """
        file_size = os.path.getsize(file_path)  # 분기 판단용(저장은 안 함)

        if file_size <= small_file_threshold:
            data = await asyncio.to_thread(self._read_all, file_path)
            gridfs_id = await self.filestore.gfs_put_bytes(
                data,
                filename=original_name,
                content_type=content_type,
                metadata={"content_type": content_type, **(meta or {})},
            )
        else:

            async def _aiter() -> AsyncIterator[bytes]:
                with open(file_path, "rb") as f:
                    while True:
                        chunk = f.read(1024 * 1024)
                        if not chunk:
                            break
                        yield chunk

            gridfs_id = await self.filestore.gfs_put_stream(
                _aiter(),
                filename=original_name,
                content_type=content_type,
                metadata={"content_type": content_type, **(meta or {})},
            )

        vm_file_id = await self.dao.insert(
            vm_project_id=vm_project_id,
            kind=kind,
            gridfs_id=gridfs_id,
            original_name=original_name,
            content_type=content_type,
            meta=meta or {},
        )
        return vm_file_id

    @staticmethod
    def _read_all(path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()
