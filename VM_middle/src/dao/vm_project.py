# src/dao/vm_project.py
from __future__ import annotations
from typing import Optional, Dict, List, Any
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
        process_annotations: Optional[list[dict]] = None,
        proj_name: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> ObjectId:
        doc = {
            "source": source,
            "gid": gid,
            "aid": aid,
            "eid": eid,
            "wpid": wpid,
            "status": "ready",  # 이후 validation으로 ready/needs-fix 덮임
            "latest_files": {},
            "project_file_draft": project_file_draft or {},
            "process_annotations": process_annotations or [],
            "proj_name": proj_name,
            "display_name": display_name,
            "validation": {"is_valid": None, "errors": [], "updated_at": _now_iso()},
            # 👇 VM 시스템 연동용 필드들 (나열형, 최소 정보만)
            "vm_job_id": None,
            "vm_last_polled_at": None,
            "vm_error_message": None,
            "vm_raw_status": None,  # 선택: 디버그용
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
        process_annotations: Optional[list[dict]] = None,
    ) -> ObjectId:
        doc = {
            "source": source,
            "gid": gid,
            "aid": aid,
            "eid": eid,
            "wpid": wpid,
            "status": "ready",  # 이후 validation으로 ready/needs-fix 덮임
            "latest_files": {},
            "project_file_draft": project_file_draft or {},
            "process_annotations": process_annotations or [],
            "proj_name": None,
            "validation": {"is_valid": None, "errors": [], "updated_at": _now_iso()},
            # 👇 VM 시스템 연동용 필드들 (나열형, 최소 정보만)
            "vm_job_id": None,
            "vm_last_polled_at": None,
            "vm_error_message": None,
            "vm_raw_status": None,  # 선택: 디버그용
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

    async def update_process_annotations(
        self, _id: ObjectId, annotations: list[dict]
    ) -> None:
        await self.col.update_one(
            {"_id": _id},
            {
                "$set": {
                    "process_annotations": annotations,
                    "updated_at": _now_iso(),
                }
            },
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

    async def set_vm_job_id(self, vm_project_id: ObjectId, job_id: str) -> None:
        await self.col.update_one(
            {"_id": vm_project_id},
            {
                "$set": {
                    "vm_job_id": job_id,
                    "vm_last_polled_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            },
        )

    async def update_vm_poll_info(
        self,
        vm_project_id: ObjectId,
        *,
        vm_raw_status: str | None = None,
        vm_error_message: str | None = None,
        project_status: str | None = None,  # completed / failed / running 등
    ) -> None:
        update: dict = {
            "vm_last_polled_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        if vm_raw_status is not None:
            update["vm_raw_status"] = vm_raw_status
        if vm_error_message is not None:
            update["vm_error_message"] = vm_error_message
        if project_status is not None:
            update["status"] = project_status

        await self.col.update_one(
            {"_id": vm_project_id},
            {"$set": update},
        )

    async def set_vm_job_started(
        self,
        vm_project_id: ObjectId,
        *,
        vm_job_id: str,
        vm_state: str | None,
        upload_mode: str = "file",
        upload_result: bool = True,
    ) -> None:
        await self.col.update_one(
            {"_id": vm_project_id},
            {
                "$set": {
                    "status": "running",
                    "vm_job_id": vm_job_id,
                    "vm_last_polled_at": _now_iso(),
                    "vm_error_message": None,
                    "vm_raw_status": vm_state,
                    "upload_mode": upload_mode,
                    "upload_result": upload_result,
                    "vm_result_upload": {
                        "mode": upload_mode,
                        "seq_id": None,
                        "total_count": 0,
                        "uploaded_indices": [],
                        "uploaded_element_ids": [],
                        "last_uploaded_index": None,
                        "last_uploaded_element_id": None,
                        "failed_index": None,
                        "error_message": None,
                        "updated_at": _now_iso(),
                    },
                    "vm_dt_file_upload_attempts": 0,
                    "updated_at": _now_iso(),
                }
            },
        )

    async def set_vm_result_upload(
        self,
        vm_project_id: ObjectId,
        *,
        upload_info: Dict[str, Any],
        project_status: str | None = None,
        vm_raw_status: str | None = None,
        vm_error_message: str | None = None,
    ) -> None:
        update: Dict[str, Any] = {
            "vm_result_upload": upload_info,
            "updated_at": _now_iso(),
        }
        if project_status is not None:
            update["status"] = project_status
        if vm_raw_status is not None:
            update["vm_raw_status"] = vm_raw_status
        if vm_error_message is not None:
            update["vm_error_message"] = vm_error_message
        await self.col.update_one({"_id": vm_project_id}, {"$set": update})

    async def set_vm_error(
        self,
        vm_project_id: ObjectId,
        *,
        message: str,
        vm_raw_status: Optional[Dict[str, Any]] = None,
    ) -> None:
        # 상태는 그대로 두되(ready 유지), 에러 메시지만 기록
        await self.col.update_one(
            {"_id": vm_project_id},
            {
                "$set": {
                    "vm_error_message": message,
                    "vm_raw_status": vm_raw_status or {},
                    "updated_at": _now_iso(),
                }
            },
        )

    async def set_vm_poll_result(
        self,
        vm_project_id: ObjectId,
        *,
        status: str,  # "running" | "completed" | "failed"
        vm_state: str | None,
        vm_error_message: str | None,
    ) -> None:
        await self.col.update_one(
            {"_id": vm_project_id},
            {
                "$set": {
                    "status": status,
                    "vm_last_polled_at": _now_iso(),
                    "vm_error_message": vm_error_message,
                    "vm_raw_status": vm_state,  # ← 마지막으로 받은 state만 저장
                    "updated_at": _now_iso(),
                }
            },
        )

    async def set_dt_file_upload_failed(
        self,
        vm_project_id: ObjectId,
        *,
        attempts: int,
        message: str,
        vm_raw_status: Optional[str],
    ) -> None:
        """
        dt_file 플랫폼 업로드 실패 기록. status는 running 유지, 재시도 횟수·에러 메시지만 갱신.
        """
        await self.col.update_one(
            {"_id": vm_project_id},
            {
                "$set": {
                    "vm_dt_file_upload_attempts": attempts,
                    "vm_error_message": message,
                    "vm_raw_status": vm_raw_status,
                    "updated_at": _now_iso(),
                }
            },
        )

    async def reset_failed_to_ready(self, vm_project_id: ObjectId) -> bool:
        res = await self.col.update_one(
            {"_id": vm_project_id, "status": "failed"},
            {
                "$set": {
                    "status": "ready",
                    "vm_job_id": None,
                    "vm_error_message": None,
                    "vm_raw_status": None,
                    "vm_last_polled_at": None,
                    "vm_result_upload": None,
                    "vm_dt_file_upload_attempts": 0,
                    "updated_at": _now_iso(),
                }
            },
        )
        return res.matched_count > 0

    async def list_running_ids(self) -> list[ObjectId]:
        """
        status='running' 인 vm_project 의 _id 목록만 반환
        """
        cursor = self.col.find({"status": "running"}, {"_id": 1})
        ids: list[ObjectId] = []
        async for doc in cursor:
            _id = doc.get("_id")
            if isinstance(_id, ObjectId):
                ids.append(_id)
        return ids
