# src/core/db.py
from __future__ import annotations
from typing import Optional
from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorGridFSBucket,
)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None
_gfs: Optional[AsyncIOMotorGridFSBucket] = None


async def connect(uri: str, db_name: str) -> None:
    global _client, _db, _gfs
    if _client:
        return
    _client = AsyncIOMotorClient(uri)
    _db = _client[db_name]
    _gfs = AsyncIOMotorGridFSBucket(_db, bucket_name="files")

    # ---------- vm_project ----------
    # (A) 부분 인덱스: 필드 존재 + 타입만 체크 (빈 문자열 여부는 검사하지 않음)
    try:
        await _db.vm_project.create_index(
            [
                ("source", 1),
                ("gid", 1),
                ("aid", 1),
                ("eid", 1),
                ("wpid", 1),
                ("created_at", -1),
            ],
            name="vmproj_tuple_created_desc",
            partialFilterExpression={
                "source": {"$exists": True, "$type": "string"},
                "gid": {"$exists": True, "$type": "string"},
                "aid": {"$exists": True, "$type": "string"},
                "eid": {"$exists": True, "$type": "string"},
                "wpid": {"$exists": True, "$type": "string"},
            },
        )
    except Exception:
        # (B) 폴백: partial 없이 동일 키로 인덱스 생성
        await _db.vm_project.create_index(
            [
                ("source", 1),
                ("gid", 1),
                ("aid", 1),
                ("eid", 1),
                ("wpid", 1),
                ("created_at", -1),
            ],
            name="vmproj_tuple_created_desc",
        )

    await _db.vm_project.create_index(
        [("status", 1), ("created_at", -1)],
        name="vmproj_status_created_desc",
    )
    await _db.vm_project.create_index(
        [("vm_id", 1)],
        name="vmproj_vm_id",
        sparse=True,
    )

    # ---------- vm_file ----------
    # A안(파일 독립 컬렉션, 프로젝트가 참조하지 않음): 프로젝트별/종류별 최신 파일 조회 최적화
    await _db.vm_file.create_index(
        [("vm_project_id", 1), ("kind", 1), ("created_at", -1)],
        name="vmfile_proj_kind_created_desc",
    )
    await _db.vm_file.create_index(
        [("vm_project_id", 1), ("created_at", -1)],
        name="vmfile_proj_created_desc",
    )

    # 선택) 원본 ISO 식별자를 자주 조회할 경우를 대비한 보조 인덱스
    # (파일명은 항상 ncdata.zip로 고정이므로 meta 기반 탐색을 돕는다)
    await _db.vm_file.create_index(
        [
            ("meta.origin.gid", 1),
            ("meta.origin.aid", 1),
            ("meta.origin.eid", 1),
            ("created_at", -1),
        ],
        name="vmfile_origin_triplet_created_desc",
        sparse=True,
    )


async def close() -> None:
    global _client, _db, _gfs
    if _client:
        _client.close()
    _client = _db = _gfs = None


def get_db() -> AsyncIOMotorDatabase:
    assert _db is not None, "Mongo not connected"
    return _db


def get_gfs() -> AsyncIOMotorGridFSBucket:
    assert _gfs is not None, "GridFS bucket not initialized"
    return _gfs
