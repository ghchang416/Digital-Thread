from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorGridFSBucket, AsyncIOMotorCollection 
from src.services.project import ProjectService
from src.services.machine import MachineService
from src.database import get_grid_fs, get_project_collection, get_product_log_collection

async def get_project_service(
    collection: AsyncIOMotorCollection = Depends(get_project_collection),
    grid_fs: AsyncIOMotorGridFSBucket = Depends(get_grid_fs),
    product_log_collection: AsyncIOMotorCollection = Depends(get_product_log_collection)
):
    return ProjectService(collection, grid_fs, product_log_collection)

async def get_file_service(
    grid_fs: AsyncIOMotorGridFSBucket = Depends(get_grid_fs),
    product_log_collection: AsyncIOMotorCollection = Depends(get_product_log_collection)
):
    return MachineService(grid_fs, product_log_collection)