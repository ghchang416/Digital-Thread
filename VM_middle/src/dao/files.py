# src/dao/files.py
from __future__ import annotations
from typing import Optional, AsyncIterator
from io import BytesIO
from bson import ObjectId
from src.core.db import get_gfs


class GridFSFileStore:
    async def gfs_put_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        chunk_size_bytes: int = 255 * 1024,
    ) -> ObjectId:
        gfs = get_gfs()
        meta = dict(metadata or {})
        if content_type:
            meta.setdefault("content_type", content_type)  # ← 여기로 병합
        oid: ObjectId = await gfs.upload_from_stream(
            filename=filename,
            source=data,
            chunk_size_bytes=chunk_size_bytes,
            metadata=meta,  # ← content_type 제거, metadata만 전달
        )
        return oid

    async def gfs_put_stream(
        self,
        it: AsyncIterator[bytes],
        *,
        filename: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        chunk_size_bytes: int = 1 * 1024 * 1024,
    ) -> ObjectId:
        gfs = get_gfs()
        meta = dict(metadata or {})
        if content_type:
            meta.setdefault("content_type", content_type)  # ← 병합
        gridin = await gfs.open_upload_stream(
            filename=filename,
            chunk_size_bytes=chunk_size_bytes,
            metadata=meta,  # ← content_type 제거
        )
        try:
            async for chunk in it:
                await gridin.write(chunk)
        finally:
            await gridin.close()
        return gridin._id  # type: ignore[attr-defined]

    async def gfs_get_bytes(self, file_id: ObjectId) -> bytes:
        gfs = get_gfs()
        buf = BytesIO()
        await gfs.download_to_stream(file_id, buf)
        return buf.getvalue()

    async def gfs_replace(
        self,
        new_data: bytes,
        *,
        filename: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> ObjectId:
        # 교체는 put 후 호출부에서 기존 파일 삭제
        return await self.gfs_put_bytes(
            new_data,
            filename=filename,
            content_type=content_type,
            metadata=metadata,
        )

    async def gfs_delete(self, file_id: ObjectId) -> None:
        gfs = get_gfs()
        await gfs.delete(file_id)
