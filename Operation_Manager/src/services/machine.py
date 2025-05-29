import asyncio
from io import BytesIO
import os
import uuid
import httpx
from fastapi import BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from src.schemas.machine import MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse
from src.entities.file import FileRepository
from src.utils.exceptions import CustomException, ExceptionEnum

class MachineService:
    gateway_base_url = os.getenv("TORUS_GATEWAY_URL", "http://localhost:5000")
    
    def __init__(self, grid_fs: AsyncIOMotorGridFSBucket):
        self.repository = FileRepository(grid_fs)
    
    async def get_machine_list(self) -> MachineListResponse:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.gateway_base_url}/machine/list")
                response.raise_for_status()
                raw_data = response.json()
                machine_list = raw_data.get("value", [])
                return MachineListResponse(machines=machine_list)
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)


    async def upload_torus_file(self, project_id: str, machine_id: int, file_id: str, background_tasks: BackgroundTasks) -> MachineFileUploadResponse:
        try:
            # 1. 파일 바이트와 이름을 함께 받아오기
            byte_io, filename = await self.repository.get_file_byteio_and_name(file_id)
            byte_io.seek(0)

            ncpath = f"/{filename}"  # ex: /O0001.nc

            files = {
                "file": (filename, byte_io, "application/octet-stream")
            }
            params = {
                "machine": machine_id,
                "ncpath": ncpath
            }

            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.gateway_base_url}/file/machine/ncpath",
                    files=files,
                    params=params
                )
                response.raise_for_status()
                result = response.json()
                background_tasks.add_task(self._monitor_machine_state, project_id, machine_id)
                return MachineFileUploadResponse(
                    status=result.get("status", -1),
                    filename=filename,
                    machine_id=machine_id,
                    ncpath=ncpath
                )
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, str(e))

    async def get_machine_status(self, machine_id: int):
        try:
            params = {'machine': machine_id, 'channel': 1}
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.gateway_base_url}/machine/channel/currentProgram/programMode",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                program_mode = data.get("value", [None])[0]
                return MachineProgramStatusResponse(programMode=program_mode)
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
        
    async def _monitor_machine_state(self, project_id: str, machine_id: int):
        mode = 0
        pname = ""
        uuid_index = 0

        product_uuid = str(uuid.uuid4())
        recipe_uuid = ""

        while True:
            status: MachineProgramStatusResponse = self.get_machine_status(machine_id=machine_id)

            if status.programMode == 1 and mode != 3:
                mode = 3
                self._add_product(project_id, product_uuid, uuid_index)
                uuid_index += 1

            # if current_program != pname and mode == 3:
            #     recipe_uuid = str(uuid.uuid4())
            #     add_product(project_id, recipe_uuid, upload_data, uuid_index)
            #     uuid_index += 1
            #     pname = current_program

            if status.programMode != 1 and mode == 3:
                break

            await asyncio.sleep(1)
        pass
    
    async def _add_product(self, project_id, product_uuid, uuid_index):
        pass