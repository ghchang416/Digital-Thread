from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorGridFSBucket, AsyncIOMotorCollection
from src.services.file import FileService
from src.services.project import ProjectService
from src.database import get_grid_fs, get_project_collection

# asset 테스트용 코드 추가
from src.services.asset_project import AssetProjectService


async def get_file_service(grid_fs: AsyncIOMotorGridFSBucket = Depends(get_grid_fs)):
    return FileService(grid_fs)


async def get_project_service(
    collection: AsyncIOMotorCollection = Depends(get_project_collection),
):
    return ProjectService(collection)


# asset 테스트용 코드 추가
async def get_asset_project_service(
    collection: AsyncIOMotorCollection = Depends(get_project_collection),
):
    return AssetProjectService(collection)
