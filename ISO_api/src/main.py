from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from src.apis.project import router as project_router
from src.apis.upload_file import router as upload_file_router
from src.apis.download_file import router as download_file_router
from src.apis.convert import router as convert_router
from src.utils.exceptions import CustomException
from fastapi_mcp import FastApiMCP
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("python_multipart").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI()

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

mcp = FastApiMCP(
    app,  
    name="My API MCP",
    description="MCP server for my API",
)
mcp.mount()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)