from fastapi import FastAPI
from src.core.config import settings
from src.core import db
from src.api.v1.iso import router as iso_router
from src.api.v1.vm_project import router as vm_project_router

import asyncio

from src.core.config import settings
from src.core.db import get_db
from src.database import get_gridfs_filestore  # 네가 올린 파일 기준
from src.dao.vm_project import VmProjectDAO
from src.dao.vm_file import VmFileDAO
from src.dao.files import GridFSFileStore
from src.services.vm_file import VmFileService
from src.services.vm_project import VmProjectService


import logging

logger = logging.getLogger(__name__)

app = FastAPI(title="VM Middleware")


@app.on_event("startup")
async def on_start():
    # 1) Mongo 연결
    await db.connect(settings.MONGO_URI, settings.MONGO_DB)

    # 2) DB 핸들 얻기 (이미 connect 된 상태에서)
    database = get_db()

    # 3) 컬렉션 준비
    vm_project_col = database["vm_project"]
    vm_file_col = database["vm_file"]

    # 4) DAO / FileStore / Service 인스턴스 구성
    vm_project_dao = VmProjectDAO(vm_project_col)
    vm_file_dao = VmFileDAO(vm_file_col)

    filestore: GridFSFileStore = get_gridfs_filestore()
    vm_file_svc = VmFileService(vm_file_dao, filestore)
    vm_project_svc = VmProjectService(vm_project_dao, vm_file_svc)

    # 5) 폴링 간격 설정 (env에서 설정 가능, 없으면 300초)
    interval = getattr(settings, "VM_POLL_INTERVAL_SEC", 300)

    logger.info("Starting VM polling loop (interval=%s sec)", interval)

    # 6) 백그라운드 태스크로 폴링 루프 시작
    asyncio.create_task(vm_project_svc.vm_polling_loop(interval_sec=interval))


@app.on_event("shutdown")
async def on_stop():
    await db.close()


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.include_router(iso_router, prefix="/api/v1")
app.include_router(vm_project_router, prefix="/api/v1")
