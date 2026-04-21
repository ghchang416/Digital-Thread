from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi
from src.apis.project import router as project_router
from src.apis.upload_file import router as upload_file_router
from src.apis.download_file import router as download_file_router
from src.apis.convert import router as convert_router

# asset 테스트용
from src.apis.v2.asset_project import router as asset_project_router
from src.apis.v2.asset_upload_file import router as asset_upload_file_router
from src.apis.v2.asset_download_file import router as asset_download_file_router

# v3 라우터
from src.apis.v3.asset import router as asset_router
from src.apis.v3.project import router as v3_project_router

# v3 중복 검사를 위한 인덱스 생성
from src.database import get_db, ensure_asset_indexes

from src.utils.exceptions import CustomException
from fastapi_mcp import FastApiMCP
import logging


logging.basicConfig(level=logging.DEBUG)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI()


def _fix_file_upload_schemas(schema: dict) -> None:
    components = schema.get("components", {}).get("schemas", {})
    for component in components.values():
        properties = component.get("properties", {})
        for prop in properties.values():
            # 단일 파일
            if prop.get("contentMediaType") == "application/octet-stream":
                prop.pop("contentMediaType", None)
                prop["format"] = "binary"

            # 파일 배열
            items = prop.get("items")
            if (
                isinstance(items, dict)
                and items.get("contentMediaType") == "application/octet-stream"
            ):
                items.pop("contentMediaType", None)
                items["format"] = "binary"

            # anyOf / oneOf / allOf 안에 들어간 경우까지 처리
            for key in ("anyOf", "oneOf", "allOf"):
                for branch in prop.get(key, []):
                    if branch.get("contentMediaType") == "application/octet-stream":
                        branch.pop("contentMediaType", None)
                        branch["format"] = "binary"

                    branch_items = branch.get("items")
                    if (
                        isinstance(branch_items, dict)
                        and branch_items.get("contentMediaType")
                        == "application/octet-stream"
                    ):
                        branch_items.pop("contentMediaType", None)
                        branch_items["format"] = "binary"


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    _fix_file_upload_schemas(openapi_schema)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.on_event("startup")
async def on_startup():
    db = await get_db()
    await ensure_asset_indexes(db)  # 한번만 호출


@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


app.include_router(project_router)
app.include_router(upload_file_router)
app.include_router(download_file_router)
app.include_router(convert_router)
app.include_router(asset_project_router)
app.include_router(asset_upload_file_router)
app.include_router(asset_download_file_router)
app.include_router(asset_router)
app.include_router(v3_project_router)

mcp = FastApiMCP(
    app,
    name="My API MCP",
    description="MCP server for my API",
)
mcp.mount()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
