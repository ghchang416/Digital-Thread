# src/dao/vm_file.py
from __future__ import annotations
from typing import Optional, Literal
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import IndexModel, DESCENDING, ASCENDING

Kind = Literal["vm-project-json", "nc-split-zip"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


KIND_VM_PROJECT_JSON: Kind = "vm-project-json"
KIND_NC_SPLIT_ZIP: Kind = "nc-split-zip"
_ALLOWED_KINDS: set[str] = {KIND_VM_PROJECT_JSON, KIND_NC_SPLIT_ZIP}


class VmFileDAO:
    def __init__(self, col: AsyncIOMotorCollection):
        self.col = col

    async def ensure_indexes(self) -> None:
        models = [
            IndexModel([("created_at", DESCENDING)], name="created_desc"),
            IndexModel(
                [("kind", ASCENDING), ("created_at", DESCENDING)],
                name="kind_created_desc",
            ),
            IndexModel(
                [("vm_project_id", ASCENDING), ("created_at", DESCENDING)],
                name="project_created_desc",
            ),
        ]
        await self.col.create_indexes(models)

    async def insert(
        self,
        *,
        vm_project_id: ObjectId,
        kind: Kind,
        gridfs_id: ObjectId,
        original_name: Optional[str] = None,
        content_type: Optional[str] = None,
        meta: Optional[dict] = None,
    ) -> ObjectId:
        if kind not in _ALLOWED_KINDS:
            raise ValueError(f"Unsupported vm_file.kind: {kind}")

        doc = {
            "vm_project_id": vm_project_id,
            "kind": kind,
            "gridfs_id": gridfs_id,
            "original_name": original_name,
            "content_type": content_type,
            "meta": meta or {},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        res = await self.col.insert_one(doc)
        return res.inserted_id

    async def get(self, _id: ObjectId) -> Optional[dict]:
        return await self.col.find_one({"_id": _id})
