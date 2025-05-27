from io import BytesIO
import os
import httpx
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


    async def upload_torus_file(self, machine_id: int, file_id: str) -> MachineFileUploadResponse:
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