import json
import os
import tempfile
import shutil

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from src.dll_api import get_step242_instance
from src.exceptions import CustomException, ExceptionEnum

# DLL API를 FastAPI REST API로 Wrapping하는 엔드포인트 라우터
router = APIRouter()

@router.post("/convert/cad/")
async def convert_cad(file: UploadFile = File(...)):
    """
    STEP(.stp) 파일을 받아 DLL을 통해 CAD 정보(JSON)로 변환하는 API.
    내부적으로 임시 디렉터리 내 파일 저장 후 DLL 메서드 호출, 결과 JSON 반환.
    """
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix != ".stp":
        # .stp 확장자 체크
        raise CustomException(ExceptionEnum.INVALID_INPUT_FORMAT)

    # 임시 디렉터리 생성
    with tempfile.TemporaryDirectory() as tmpdir:
        stp_path = os.path.join(tmpdir, file.filename)
        # 업로드 파일 저장
        with open(stp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 결과 JSON 경로 지정
        json_output_path = os.path.join(tmpdir, file.filename.replace(suffix, "_cad.json"))
        model_id = 1

        # C# DLL 객체 생성 및 메서드 호출
        instance = get_step242_instance()
        instance.getCADdata(stp_path, json_output_path, model_id)

        # 변환 결과 파일 존재 여부 체크
        if not os.path.exists(json_output_path):
            raise CustomException(ExceptionEnum.FILE_GENERATION_FAILED)

        # 변환된 JSON 결과 반환
        with open(json_output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        return JSONResponse(content=data)
        
@router.post("/convert/gdt/")
async def convert_gdt(file: UploadFile = File(...)):
    """
    STEP(.stp) 파일을 받아 DLL을 통해 GD&T 정보(JSON)로 변환하는 API.
    내부적으로 임시 디렉터리 내 파일 저장 후 DLL 메서드 호출, 결과 JSON 반환.
    """
    suffix = os.path.splitext(file.filename)[1].lower()
    if suffix != ".stp":
        raise CustomException(ExceptionEnum.INVALID_INPUT_FORMAT)

    with tempfile.TemporaryDirectory() as tmpdir:
        stp_path = os.path.join(tmpdir, file.filename)
        with open(stp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        json_output_path = os.path.join(tmpdir, file.filename.replace(suffix, "_gdt.json"))
        model_id = 1

        # C# DLL 객체 생성 및 메서드 호출
        instance = get_step242_instance()
        instance.getGDTdata(stp_path, json_output_path, model_id)

        if not os.path.exists(json_output_path):
            raise CustomException(ExceptionEnum.FILE_GENERATION_FAILED)

        with open(json_output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        return JSONResponse(content=data)
