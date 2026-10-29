"""Isolated, read-only creator development app; no legacy startup/DB writes."""

from fastapi import FastAPI
from src.apis.v3.creator import router
from src.apis.v3.creator_middleware import BodyLimitMiddleware


app = FastAPI(title="DT Creator Foundation", version="0.1.0")
app.add_middleware(BodyLimitMiddleware)
app.include_router(router)


@app.get("/healthz")
def health():
    return {"status": "ok", "persistence": "disabled"}
