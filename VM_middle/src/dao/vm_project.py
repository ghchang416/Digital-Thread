# src/dao/vm_project.py
from __future__ import annotations
from typing import Optional, Dict, List
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import ASCENDING, DESCENDING, IndexModel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class VmProjectDAO:
    def __init__(self, col: AsyncIOMotorCollection):
        self.col = col

    async def ensure_indexes(self) -> None:
        models = [
            IndexModel(
                [("status", ASCENDING), ("updated_at", DESCENDING)],
                name="status_updated_desc",
            ),
            IndexModel([("created_at", DESCENDING)], name="created_desc"),
        ]
        await self.col.create_indexes(models)

    async def insert_initial_from_iso(
        self,
        *,
        gid: str,
        aid: str,
        eid: str,
        wpid: Optional[str],
        source: str = "iso",
        project_file_draft: Optional[dict] = None,
        proj_name: Optional[str] = None,
    ) -> ObjectId:
        doc = {
            "source": source,
            "gid": gid,
            "aid": aid,
            "eid": eid,
            "wpid": wpid,
            # 생성 시점에선 곧바로 검증해서 needs-fix/ready 로 덮일 예정
            "status": "ready",
            "latest_files": {},
            "project_file_draft": project_file_draft or {},
            "proj_name": proj_name,
            "validation": {"is_valid": None, "errors": [], "updated_at": _now_iso()},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        res = await self.col.insert_one(doc)
        return res.inserted_id

    async def set_latest_files(
        self, vm_project_id: ObjectId, latest: Dict[str, ObjectId]
    ) -> None:
        await self.col.update_one(
            {"_id": vm_project_id},
            {"$set": {"latest_files": latest, "updated_at": _now_iso()}},
        )

    async def patch_latest_file(
        self, vm_project_id: ObjectId, kind: str, vm_file_id: ObjectId
    ) -> None:
        await self.col.update_one(
            {"_id": vm_project_id},
            {"$set": {f"latest_files.{kind}": vm_file_id, "updated_at": _now_iso()}},
        )

    async def set_status(self, vm_project_id: ObjectId, status: str) -> None:
        await self.col.update_one(
            {"_id": vm_project_id},
            {"$set": {"status": status, "updated_at": _now_iso()}},
        )

    async def set_validation_result(
        self,
        vm_project_id: ObjectId,
        *,
        is_valid: bool,
        errors: List[str],
        next_status_if_valid: str = "ready",
        next_status_if_invalid: str = "needs-fix",
    ) -> None:
        status = next_status_if_valid if is_valid else next_status_if_invalid
        await self.col.update_one(
            {"_id": vm_project_id},
            {
                "$set": {
                    "status": status,
                    "validation": {
                        "is_valid": is_valid,
                        "errors": errors,
                        "updated_at": _now_iso(),
                    },
                    "updated_at": _now_iso(),
                }
            },
        )

    async def get(self, _id: ObjectId) -> Optional[dict]:
        return await self.col.find_one({"_id": _id})

    async def insert_draft_from_iso(
        self,
        *,
        source: str,
        gid: str,
        aid: str,
        eid: str,
        wpid: Optional[str],
        project_file_draft: dict,
    ) -> ObjectId:
        doc = {
            "source": source,
            "gid": gid,
            "aid": aid,
            "eid": eid,
            "wpid": wpid,
            "status": "ready",  # 곧바로 검증으로 덮임
            "latest_files": {},
            "project_file_draft": project_file_draft,
            "validation": {"is_valid": None, "errors": [], "updated_at": _now_iso()},
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        res = await self.col.insert_one(doc)
        return res.inserted_id

    async def update_project_file_draft(
        self, _id: ObjectId, project_file: dict
    ) -> None:
        await self.col.update_one(
            {"_id": _id},
            {"$set": {"project_file_draft": project_file, "updated_at": _now_iso()}},
        )

    async def list_projects(
        self,
        *,
        status: str | None = None,
        gid: str | None = None,
        aid: str | None = None,
        q: str | None = None,  # proj_name / eid 간단 검색
        page: int = 1,
        size: int = 20,
        sort: list[tuple[str, int]] | None = None,  # 기본 updated_at desc
    ) -> tuple[list[dict], int]:
        filt: dict = {}
        if status:
            filt["status"] = status
        if gid:
            filt["gid"] = gid
        if aid:
            filt["aid"] = aid
        if q:
            # 간단 텍스트 검색: proj_name / eid 부분일치
            filt["$or"] = [
                {"proj_name": {"$regex": q, "$options": "i"}},
                {"eid": {"$regex": q, "$options": "i"}},
            ]

        page = max(1, int(page))
        size = min(100, max(1, int(size)))
        skip = (page - 1) * size
        sort = sort or [("updated_at", DESCENDING)]

        total = await self.col.count_documents(filt)
        cursor = self.col.find(filt).sort(sort).skip(skip).limit(size)
        items = await cursor.to_list(length=size)
        return items, total
