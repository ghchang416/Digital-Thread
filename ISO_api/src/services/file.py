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
    DLL_URI = os.getenv("DLL_URI", "http://dll-server:8010")
    
    def __init__(self, grid_fs: AsyncIOMotorGridFSBucket):
        self.repository = FileRepository(grid_fs)
        
    async def delete_project_files(self, project: dict):
        file_ids = []
        for key, value in project.items():
            if key not in ["_id", "data"]: 
                if isinstance(value, list):
                    file_ids.extend(value)
                else:
                    file_ids.append(value) 

        delete_tasks = [self.repository.delete_file_by_id(file_id) for file_id in file_ids]
        deleted_files = await asyncio.gather(*delete_tasks)
        return
    
    async def delete_file_by_id(self, file_id: str):
        await self.repository.delete_file_by_id(file_id)
        return
    
    async def process_upload(self, file: UploadFile, metadata: Optional[dict] = None):
        step_content = await file.read()
        filename = file.filename
        file_id = await self.repository.insert_file(step_content, filename, metadata=metadata)
        return file_id

    async def file_exist(self, file_id: str):
        exists = await self.repository.file_exists(file_id)
        if not exists:
            raise CustomException(ExceptionEnum.NC_NOT_EXIST)
        return

    async def get_file_stream(self, file_id: str) -> str:
        return await self.repository.get_file(file_id)
    
    async def stp_upload(self, step_file: UploadFile):
        step_content = await step_file.read()
        filename = step_file.filename

        stl_filename = await self.stl_convert(step_content)
        step_file_id = await self.repository.insert_file(step_content, filename)

        with open(stl_filename, "rb") as stl_file:
            stl_content = stl_file.read()
            stl_file_id = await self.repository.insert_file(stl_content, filename.replace(".STEP", ".stl"))

        os.remove(stl_filename)

        return {"step_id": step_file_id, "stl_id": stl_file_id}
    
    async def stl_convert(self, step_content: bytes) -> str:
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
        file_stream = await self.repository.get_file_byteio(step_id)
        filename = f"{step_id}.stp"
        result = await self._send_to_conversion_api(file_stream, filename, type)
        return result
    
    async def _send_to_conversion_api(self, file_bytes: BytesIO, filename: str, type: str) -> bytes:
        file_bytes.seek(0)
        files = {'file': (filename, file_bytes, 'application/octet-stream')}
        async with httpx.AsyncClient() as client:
            if type == "cad":
                response = await client.post(self.DLL_URI + "/convert/cad/", files=files)
            else:
                response = await client.post(self.DLL_URI + "/convert/gdt/", files=files)
            response.raise_for_status()
            return response.content 
