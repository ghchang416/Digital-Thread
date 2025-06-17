import asyncio
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.apis.project import router as project_router
from src.apis.machine import router as machine_router
from src.utils.exceptions import CustomException
from src.database import get_grid_fs_raw, get_product_log_collection_raw
from src.services.machine import MachineService
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def start_tracking_all_machines():
    grid_fs = get_grid_fs_raw()
    product_log_collection = get_product_log_collection_raw()
    machine_service = MachineService(grid_fs, product_log_collection)
    asyncio.create_task(machine_service.track_all_machines_forever())
    
@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

app.include_router(project_router)
app.include_router(machine_router)