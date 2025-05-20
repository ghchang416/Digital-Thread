import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.exceptions import CustomException
from src.apis import router as dll_router

logging.basicConfig(level=logging.INFO)

app = FastAPI()

@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

app.include_router(dll_router)