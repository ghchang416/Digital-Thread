from fastapi import FastAPI
from src.core.config import settings
from src.core import db
from src.api.v1.iso import router as iso_router
from src.api.v1.vm_project import router as vm_project_router

app = FastAPI(title="VM Middleware")


@app.on_event("startup")
async def on_start():
    await db.connect(settings.MONGO_URI, settings.MONGO_DB)


@app.on_event("shutdown")
async def on_stop():
    await db.close()


@app.get("/healthz")
async def healthz():
    return {"ok": True}


app.include_router(iso_router, prefix="/api/v1")
app.include_router(vm_project_router, prefix="/api/v1")
