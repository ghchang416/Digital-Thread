import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.exceptions import CustomException
from src.apis import router as dll_router

logging.basicConfig(level=logging.INFO)

# FastAPI 앱 생성
app = FastAPI()

# 커스텀 예외 핸들러 등록 (커스텀 예외 발생 시 일관된 에러 응답)
@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

# DLL API 라우터 등록
app.include_router(dll_router)
