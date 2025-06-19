from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket, AsyncIOMotorDatabase, AsyncIOMotorCollection
from dotenv import load_dotenv
from functools import lru_cache
from fastapi import Depends
import os

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongo:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "iso14649")

@lru_cache()
def get_motor_client() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(MONGO_URL)

async def get_db() -> AsyncIOMotorDatabase:
    return get_motor_client()[DATABASE_NAME]

async def get_grid_fs(db: Optional[AsyncIOMotorDatabase]):
    if db is None: 
        db = await get_db()
    return AsyncIOMotorGridFSBucket(db, bucket_name="files")