from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket, AsyncIOMotorDatabase
from dotenv import load_dotenv
from functools import lru_cache
from fastapi import Depends
import os

# --- 환경 변수 로드 (.env 파일) ---
load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iso14649")

@lru_cache()
def get_motor_client() -> AsyncIOMotorClient:
    """
    MongoDB 클라이언트(싱글턴) 반환.
    - lru_cache()로 싱글턴 생성 (FastAPI 권장)
    """
    return AsyncIOMotorClient(MONGO_URL)

async def get_db() -> AsyncIOMotorDatabase:
    """
    비동기 MongoDB 데이터베이스 핸들러 반환.
    - FastAPI Dependency(Depends)로 주입 시 사용
    - 예시: db = Depends(get_db)
    """
    return get_motor_client()[DATABASE_NAME]

async def get_grid_fs(db: Optional[AsyncIOMotorDatabase]):
    """
    GridFS 버킷 핸들러를 반환.
    - 주의: db가 None이면 내부에서 get_db() 호출
    - 파일 저장/조회 시 활용
    """
    if db is None: 
        db = await get_db()
    return AsyncIOMotorGridFSBucket(db, bucket_name="files")
