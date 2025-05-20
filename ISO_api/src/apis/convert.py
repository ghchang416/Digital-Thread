import json
from typing import Optional
from fastapi import APIRouter, Depends, File, Path, Body, Query, UploadFile
from src.services import get_file_service, FileService, ProjectService, get_project_service
from src.schemas.file import FileCreateResponse, StpCreateResponse
from src.utils.exceptions import CustomException, ExceptionEnum

router = APIRouter(prefix="/api/convert", tags=["STP Convert"])

"""
==============================================  파일 변환 API ==============================================
"""

@router.get("/cad", status_code=200, summary="STEP to CAD 변환")
async def convert_from_step_to_cad(
    project_id: str = Query(..., description="프로젝트의 ID"),
    stp_id: str = Query(..., description="STP ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    project: dict | None = await project_service.get_project_by_id(project_id)
    if not project.get("step_id"):
        raise CustomException(ExceptionEnum.STP_NOT_FOUND)
    
    cad_json_bytes = await file_service.convert_stp_to_cad(stp_id, "cad")
    cad_json = json.loads(cad_json_bytes)

    return cad_json

@router.get("/gdt", status_code=200, summary="STEP to GD&T 변환")
async def convert_from_step_to_gdt(
    project_id: str = Query(..., description="프로젝트의 ID"),
    stp_id: str = Query(..., description="STP ID"),
    project_service: ProjectService = Depends(get_project_service),
    file_service: FileService = Depends(get_file_service),
):
    project: dict | None = await project_service.get_project_by_id(project_id)
    if not project.get("step_id"):
        raise CustomException(ExceptionEnum.STP_NOT_FOUND)
    
    gdt_json_bytes = await file_service.convert_stp_to_cad(stp_id, "gdt")
    gdt_json = json.loads(gdt_json_bytes)

    return gdt_json
