import json
import os
import tempfile
import shutil

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from src.dll_api import get_step242_instance
from src.exceptions import CustomException, ExceptionEnum

router = APIRouter()

@router.post("/convert/cad/")
async def convert_cad(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix != ".stp":
        raise CustomException(ExceptionEnum.INVALID_INPUT_FORMAT)

    with tempfile.TemporaryDirectory() as tmpdir:
        stp_path = os.path.join(tmpdir, file.filename)
        with open(stp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        json_output_path = os.path.join(tmpdir, file.filename.replace(suffix, "_cad.json"))
        model_id = 1

        instance = get_step242_instance()
        instance.getCADdata(stp_path, json_output_path, model_id)

        if not os.path.exists(json_output_path):
            raise CustomException(ExceptionEnum.FILE_GENERATION_FAILED)

        with open(json_output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        return JSONResponse(content=data)
        
@router.post("/convert/gdt/")
async def convert_gdt(file: UploadFile = File(...)):
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix != ".stp":
        raise CustomException(ExceptionEnum.INVALID_INPUT_FORMAT)

    with tempfile.TemporaryDirectory() as tmpdir:
        stp_path = os.path.join(tmpdir, file.filename)
        with open(stp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        json_output_path = os.path.join(tmpdir, file.filename.replace(suffix, "_gdt.json"))
        model_id = 1

        instance = get_step242_instance()
        instance.getGDTdata(stp_path, json_output_path, model_id)

        if not os.path.exists(json_output_path):
            raise CustomException(ExceptionEnum.FILE_GENERATION_FAILED)

        with open(json_output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        return JSONResponse(content=data)

