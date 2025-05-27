from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorGridFSBucket, AsyncIOMotorCollection 
from src.services.project import ProjectService
from src.services.machine import MachineService
from src.database import get_grid_fs, get_project_collection

async def get_project_service(
    collection: AsyncIOMotorCollection = Depends(get_project_collection)
):
    return ProjectService(collection)

async def get_file_service(
    grid_fs: AsyncIOMotorGridFSBucket = Depends(get_grid_fs)
):
    return MachineService(grid_fs)