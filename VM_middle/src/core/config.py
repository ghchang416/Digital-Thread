# src/core/config.py
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 공통
    APP_ENV: str = "local"
    LOG_LEVEL: str = "INFO"
    TZ: str = "Asia/Seoul"

    # Mongo
    # compose 서비스명이 'mongo'면 OK (container_name은 DNS 이름이 아님)
    MONGO_URI: str = "mongodb://mongo:27017"
    MONGO_DB: str = "vm_mw"

    # External endpoints
    SOURCE_DEFAULT: str = "iso"  # iso|dp
    ISO_API_URL: AnyHttpUrl | str = "http://iso-api:8000"
    ISO_PATH_GLOBALS: str = "/api/v3/assets/global-assets"  # 글로벌 에셋 ID 목록
    ISO_PATH_PROJECTS: str = (
        "/api/v3/projects"  # global_asset_id= 로 프로젝트 목록 조회
    )
    ISO_PATH_PROJECT_DETAIL: str = "/api/v3/projects/{element_id}"
    ISO_PATH_ASSET_DETAIL: str = "/api/v3/assets/{element_id}"
    ISO_PATH_FILE_DOWNLOAD_BY_KEYS: str = "/api/v3/assets/file-download"
    ISO_PATH_ASSET_LIST: str = "/api/v3/assets"

    DP_API_URL: AnyHttpUrl | str = "http://220.75.173.230:20220"

    # VM 서버 (기본값 제공)
    VM_API_URL: AnyHttpUrl = "https://api.unicncsolutions.com"
    VM_USERNAME: str = "vajura86@kitech.re.kr"
    VM_PASSWORD: str = "tkQhdtka*6"
    VM_S3_UPLOAD_DETAIL: str = "/s3-upload"
    VM_LOGIN_TOKEN: str = "/api/v1/auths/login/access-token"
    VM_JOB_CREATE: str = "/api/v1/macsim"
    VM_GET_JOB_DETAIL_PATH: str = "/api/v1/macsim/{macsim_id}"

    POLL_INTERVAL_SEC: int = 20
    POLL_TIMEOUT_SEC: int = 7200

    # HTTP 클라이언트 설정
    HTTP_TIMEOUT_SEC: float = 15.0
    HTTP_RETRIES: int = 2

    DEFAULT_STOCK_TYPE: int = 9
    DEFAULT_STOCK_SIZE: str = "0,0,0,100,50,20"
    ALLOW_MISSING_TOOL_FIELDS: bool = True

    # ⬇️ v2 설정 방식
    model_config = SettingsConfigDict(
        env_file=".env",  # 로컬 실행 시 .env도 읽기
        env_file_encoding="utf-8",
        case_sensitive=False,  # 대소문자 무시 (VM_API_URL == vm_api_url)
        extra="ignore",  # 정의 밖 키 무시
    )


settings = Settings()
