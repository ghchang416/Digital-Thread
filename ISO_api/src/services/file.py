import asyncio
from io import BytesIO
import logging
import os
import tempfile
from typing import Optional
from fastapi import UploadFile
import httpx
from src.entities.file import FileRepository
from src.utils.exceptions import CustomException, ExceptionEnum
from motor.motor_asyncio import AsyncIOMotorGridFSBucket, AsyncIOMotorGridOut
from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.StlAPI import StlAPI_Writer
from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
from OCC.Core.IFSelect import IFSelect_RetDone
from dotenv import load_dotenv

load_dotenv()

class FileService:
    """
    파일 업로드/다운로드, 변환, 삭제 등 파일 관련 모든 핵심 로직을 담당하는 서비스 클래스.
    MongoDB GridFS, 외부 DLL 변환 서버(http API), OpenCASCADE 파이썬 바인딩 사용.
    """
    DLL_URI = os.getenv("DLL_URI", "http://dll-server:8010")  # 외부 DLL 변환 서버 API 주소
    
    def __init__(self, grid_fs: AsyncIOMotorGridFSBucket):
        # 파일 저장/조회 등 실제 DB 작업은 FileRepository가 담당 (의존성 주입)
        self.repository = FileRepository(grid_fs)
        
    async def delete_project_files(self, project: dict):
        """
        프로젝트 정보 내 연결된 파일 ObjectId 리스트를 추출해 전부 삭제.
        (프로젝트 내 여러 파일 종류별로 관리)
        """
        file_ids = []
        for key, value in project.items():
            if key not in ["_id", "data"]:  # _id, data 제외
                if isinstance(value, list):
                    file_ids.extend(value)
                else:
                    file_ids.append(value) 

        delete_tasks = [self.repository.delete_file_by_id(file_id) for file_id in file_ids]
        # 비동기로 병렬 삭제
        deleted_files = await asyncio.gather(*delete_tasks)
        return
    
    async def delete_file_by_id(self, file_id: str):
        """파일 ObjectId로 해당 파일을 삭제."""
        await self.repository.delete_file_by_id(file_id)
        return
    
    async def process_upload(self, file: UploadFile, metadata: Optional[dict] = None):
        """
        업로드 파일(UploadFile)을 읽어 GridFS에 저장, file_id 반환.
        """
        step_content = await file.read()
        filename = file.filename
        file_id = await self.repository.insert_file(step_content, filename, metadata=metadata)
        return file_id

    async def file_exist(self, file_id: str):
        """
        파일 존재 여부 확인. 없으면 예외 발생.
        """
        exists = await self.repository.file_exists(file_id)
        if not exists:
            raise CustomException(ExceptionEnum.NC_NOT_EXIST)
        return

    async def get_file_stream(self, file_id: str) -> str:
        """파일 ObjectId로 GridFS에서 파일 스트림 조회."""
        return await self.repository.get_file(file_id)
    
    async def stp_upload(self, step_file: UploadFile):
        """
        STEP 파일 업로드 후 STL로 변환, 둘 다 GridFS에 저장.
        변환된 파일 ID(dict) 반환: {"step_id": step_file_id, "stl_id": stl_file_id}
        """
        step_content = await step_file.read()
        filename = step_file.filename

        stl_filename = await self.stl_convert(step_content)  # STEP → STL 변환
        step_file_id = await self.repository.insert_file(step_content, filename)

        with open(stl_filename, "rb") as stl_file:
            stl_content = stl_file.read()
            stl_file_id = await self.repository.insert_file(stl_content, filename.replace(".STEP", ".stl"))

        os.remove(stl_filename)  # 임시 STL 파일 삭제

        return {"step_id": step_file_id, "stl_id": stl_file_id}
    
    async def stl_convert(self, step_content: bytes) -> str:
        """
        STEP 파일 바이너리를 STL 파일로 변환 (OpenCASCADE).
        변환된 임시 STL 파일 경로 반환 (호출부에서 직접 삭제 필요).
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=".stp") as tmp_step:
            tmp_step.write(step_content)
            tmp_step_path = tmp_step.name

        reader = STEPControl_Reader()
        status = reader.ReadFile(tmp_step_path)

        if status == IFSelect_RetDone:
            reader.TransferRoots()
            shape = reader.Shape()

            mesh = BRepMesh_IncrementalMesh(shape, 0.1)
            mesh.Perform()

            stl_path = tmp_step_path.replace(".stp", ".stl")
            stl_writer = StlAPI_Writer()
            stl_writer.Write(shape, stl_path)

            os.remove(tmp_step_path)

            return stl_path
        
    async def convert_stp_to_cad(self, step_id: str, type: str) -> bytes:
        """
        STEP 파일을 CAD/GD&T 포맷(json)으로 변환. 
        내부적으로 외부 DLL API 서버에 HTTP로 전달.
        type = "cad" or "gdt"
        """
        file_stream = await self.repository.get_file_byteio(step_id)
        filename = f"{step_id}.stp"
        result = await self._send_to_conversion_api(file_stream, filename, type)
        return result
    
    async def _send_to_conversion_api(self, file_bytes: BytesIO, filename: str, type: str) -> bytes:
        """
        외부 DLL 서버에 파일을 POST로 전송하여 CAD/GD&T 변환 결과(json) 받기.
        실패시 예외 발생.
        """
        file_bytes.seek(0)
        files = {'file': (filename, file_bytes, 'application/octet-stream')}
        async with httpx.AsyncClient() as client:
            if type == "cad":
                response = await client.post(self.DLL_URI + "/convert/cad/", files=files)
            else:
                response = await client.post(self.DLL_URI + "/convert/gdt/", files=files)
            response.raise_for_status()
            return response.content  # 변환 결과 bytes (json)
