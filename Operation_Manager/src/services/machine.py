import asyncio
from io import BytesIO
import io
import os
import uuid
import httpx
from fastapi import BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from src.schemas.machine import MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse
from src.entities.file import FileRepository
from src.utils.exceptions import CustomException, ExceptionEnum

machine_job_status = {
}

class MachineService:
    gateway_base_url = os.getenv("TORUS_GATEWAY_URL", "http://localhost:5001")
    
    def __init__(self, grid_fs: AsyncIOMotorGridFSBucket):
        self.repository = FileRepository(grid_fs)
    
    async def get_machine_list(self) -> MachineListResponse:
        """
        Torus Gateway API를 호출하여 등록된 CNC 장비 목록을 조회합니다.
        """
        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(f"{self.gateway_base_url}/machine/list")
                response.raise_for_status()
                raw_data = response.json()
                machine_list = raw_data.get("value", [])
                return MachineListResponse(machines=machine_list)
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)


    async def upload_torus_file(self, project_id: str, machine_id: int, file_id: str, background_tasks: BackgroundTasks) -> MachineFileUploadResponse:
        try:
            byte_io, filename = await self.repository.get_file_byteio_and_name(file_id)
            file_data = byte_io.read()  # raw bytes로 강제 변환
            ncpath = f"C:\\Users\\Gyeonghyun\\Documents\\TENUX\\TENUX_Emulator\\Projects\\MC_5axis_1ch\\Nc\\{filename}"  # ex: /O0001.nc

            files = {
                "file": (filename, file_data, "application/octet-stream")
            }
            params = {
                "machine": machine_id,
                "ncpath": ncpath
            }
            if machine_id not in machine_job_status:
                machine_job_status[machine_id] = {}
            machine_job_status[machine_id][filename] = "가공 대기"
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.put(
                    f"{self.gateway_base_url}/file/machine/ncpath",
                    files=files,
                    params=params
                )
                response.raise_for_status()
                result = response.json()
                # background_tasks.add_task(self._monitor_machine_state, project_id, machine_id)
                return MachineFileUploadResponse(
                    status=result.get("status", -1),
                    filename=filename,
                    machine_id=machine_id,
                    ncpath=ncpath
                )
        except Exception as e:
            print(e)
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def get_machine_status(self, machine_id: int):
        try:
            params = {'machine': machine_id, 'channel': 1}
            async with httpx.AsyncClient(verify=False) as client:
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
        
    async def get_current_program_name(self, machine_id: int) -> str:
        try:
            params = {'machine': machine_id, 'channel': 1}
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.gateway_base_url}/machine/channel/currentProgram/currentFile/programName",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                return data.get("value", [None])[0] or ""
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def update_machine_job_status(self, machine_id: int):
        # 현재 장비에서 실행 중인 프로그램명 조회
        current_program_name = await self.get_current_program_name(machine_id)  # 예: "O0002.nc"

        if machine_id not in machine_job_status:
            return {}

        for fname, status in machine_job_status[machine_id].items():
            if fname == current_program_name:
                machine_job_status[machine_id][fname] = "가공 중"
            elif status == "가공 중":
                # 더 이상 실행 중이지 않으면 요청 대기로 전환
                machine_job_status[machine_id][fname] = "요청 대기"
        return machine_job_status[machine_id]
        
    async def _monitor_machine_state(self, project_id: str, machine_id: int):
        mode = 0
        pname = ""
        uuid_index = 0

        product_uuid = str(uuid.uuid4())
        recipe_uuid = ""

        while True:
            status: MachineProgramStatusResponse = await self.get_machine_status(machine_id=machine_id)

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