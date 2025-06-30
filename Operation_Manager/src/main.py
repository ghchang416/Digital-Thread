import asyncio
from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.apis.project import router as project_router
from src.apis.machine import router as machine_router
from src.utils.exceptions import CustomException
from src.services import MachineService, get_machine_service
import logging

# --- 로깅 설정 ---
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("Operation_Manager")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# --- FastAPI 앱 인스턴스 생성 ---
app = FastAPI()

# --- CORS 미들웨어 설정 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 오리진 허용 (배포 시 제한 권장)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 서버 시작 시 모든 CNC 장비 추적 백그라운드 태스크 시작 ---
@app.on_event("startup")
async def start_tracking_all_machines():
    """
    서버 시작 시 모든 CNC 장비 상태 추적(모니터링) 루프를 백그라운드 태스크로 실행합니다.
    """
    machine_service: MachineService = await get_machine_service()
    asyncio.create_task(machine_service.track_all_machines_forever())
    
# --- CustomException 발생 시 JSON 형태로 에러 반환 ---
@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    """
    도메인 커스텀 예외(CustomException) 핸들러.
    - detail: ExceptionEnum 이름(유형)
    - extra_detail: 상세 메시지(한국어/영어 혼합 가능)
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.name,
            "extra_detail": exc.detail,  
        },
    )

# --- API 라우터 등록 ---
app.include_router(project_router)
app.include_router(machine_router)
