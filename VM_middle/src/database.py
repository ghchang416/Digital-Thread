# src/core/database.py  (혹은 네가 쓰는 경로 유지)
from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase, AsyncIOMotorCollection
from src.core.db import get_db

from src.dao.vm_project import VmProjectDAO
from src.services.vm_project import VmProjectService

from src.dao.vm_file import VmFileDAO
from src.services.vm_file import VmFileService
from src.dao.files import GridFSFileStore
from functools import lru_cache


# --- vm_project DI (기존) ---
async def get_vm_project_collection(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AsyncIOMotorCollection:
    return db["vm_project"]


async def get_vm_project_dao(
    col: AsyncIOMotorCollection = Depends(get_vm_project_collection),
) -> VmProjectDAO:
    return VmProjectDAO(col)


# --- vm_file DI (신규) ---
async def get_vm_file_collection(
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> AsyncIOMotorCollection:
    return db["vm_file"]


async def get_vm_file_dao(
    col: AsyncIOMotorCollection = Depends(get_vm_file_collection),
) -> VmFileDAO:
    return VmFileDAO(col)


@lru_cache(maxsize=1)
def get_gridfs_filestore() -> GridFSFileStore:
    return GridFSFileStore()


async def get_vm_file_service(
    dao: VmFileDAO = Depends(get_vm_file_dao),
    filestore: GridFSFileStore = Depends(get_gridfs_filestore),
) -> VmFileService:
    return VmFileService(dao, filestore)


async def get_vm_project_service(
    dao: VmProjectDAO = Depends(get_vm_project_dao),
    vm_file_svc: VmFileService = Depends(get_vm_file_service),  # ← 추가 주입
) -> VmProjectService:
    return VmProjectService(dao, vm_file_svc)  # ← 생성자 인자 2개
