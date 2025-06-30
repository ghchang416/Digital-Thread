import os
from src.repositories.file import FileRepository
from src.repositories.log import MachineLogRepository
from src.repositories.machine import MachineRepository
from src.repositories.project import ProjectRepository
from src.repositories.redis import RedisRepository
from src.database import get_db, get_grid_fs

# --- 로그 리포지토리 인스턴스 반환 (비동기, DI용) ---
async def get_log_repository() -> MachineLogRepository:
    """
    MongoDB product_logs 컬렉션 기반의 가공 로그 저장소 리포지토리 반환.
    """
    db = await get_db()
    return MachineLogRepository(db['product_logs'])

# --- 프로젝트 리포지토리 인스턴스 반환 (비동기, DI용) ---
async def get_project_repository() -> ProjectRepository:
    """
    MongoDB projects 컬렉션 기반의 프로젝트 리포지토리 반환.
    """
    db = await get_db()
    return ProjectRepository(db['projects'])

# --- Torus Gateway API 연동 리포지토리 반환 ---
async def get_machine_repository() -> MachineRepository:
    """
    Torus Gateway 외부 API와 연동하는 머신 리포지토리 반환.
    환경 변수 TORUS_GATEWAY_URL 사용
    """
    torus_url = os.getenv("TORUS_GATEWAY_URL", "http://10.10.10.49:5001")
    return MachineRepository(torus_url)

# --- 파일(GridFS) 리포지토리 반환 ---
async def get_file_repository() -> FileRepository:
    """
    MongoDB GridFS 기반의 파일(바이너리) 리포지토리 반환.
    """
    db = await get_db()
    grid_fs = await get_grid_fs(db)
    return FileRepository(grid_fs)

# --- Redis 리포지토리 반환 ---
async def get_redis_repository() -> RedisRepository:
    """
    Redis 서버와 연동하는 리포지토리 반환.
    환경 변수 REDIS_HOST, REDIS_PORT 사용
    """
    redis_host = os.getenv("REDIS_HOST", "redis")
    redis_port = int(os.getenv("REDIS_PORT", 6379))
    return RedisRepository(redis_host, redis_port)
