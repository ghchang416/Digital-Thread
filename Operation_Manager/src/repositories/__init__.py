import os
from src.repositories.file import FileRepository
from src.repositories.log import MachineLogRepository
from src.repositories.machine import MachineRepository
from src.repositories.project import ProjectRepository
from src.repositories.redis import RedisRepository

from src.database import get_db, get_grid_fs

async def get_log_repository() -> MachineLogRepository:
    db = await get_db()
    return MachineLogRepository(db['product_logs'])

async def get_project_repository() -> ProjectRepository:
    db = await get_db()
    return ProjectRepository(db['projects'])

async def get_machine_repository() -> MachineRepository:
    torus_url = os.getenv("TORUS_GATEWAY_URL", "http://host.docker.internal:5001")
    return MachineRepository(torus_url)

async def get_file_repository() -> FileRepository:
    db = await get_db()
    grid_fs = await get_grid_fs(db)
    return FileRepository(grid_fs)

async def get_redis_repository() -> RedisRepository:
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = os.getenv("REDIS_PORT", 6379)
    return RedisRepository(redis_host, redis_port)
    