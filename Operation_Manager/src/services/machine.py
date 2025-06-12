import asyncio
from datetime import datetime
import os
import uuid
import httpx
from src.services.redis import RedisJobTracker
from fastapi import BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorGridFSBucket, AsyncIOMotorCollection
from src.schemas.machine import MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse
from src.entities.file import FileRepository
from src.utils.exceptions import CustomException, ExceptionEnum
import logging

logger = logging.getLogger("machine_tracker")
logging.basicConfig(
    level=logging.INFO,  # info 로그까지 보이도록 설정
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


class MachineService:
    gateway_base_url = os.getenv("TORUS_GATEWAY_URL", "http://host.docker.internal:5000")
    
    def __init__(self, grid_fs: AsyncIOMotorGridFSBucket, product_log_collection: AsyncIOMotorCollection):
        self.repository = FileRepository(grid_fs)
        self.nc_root_paths = {}
        self.product_log_collection = product_log_collection
        self.redis_tracker = RedisJobTracker() 


    async def _get_nc_root_path(self, machine_id: int) -> str:
        if machine_id in self.nc_root_paths:
            return self.nc_root_paths[machine_id]
        
        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.gateway_base_url}/machine/ncMemory/rootPath",
                    params={"machine": machine_id}
                )
                response.raise_for_status()
                data = response.json()
                root_path = data.get("value", "")[0]
                if not root_path:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                self.nc_root_paths[machine_id] = root_path
                return root_path
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
    
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
            file_data = byte_io.read()
            ncpath = await self._get_nc_root_path(machine_id)

            files = {
                "file": (filename, file_data, "application/octet-stream")
            }
            params = {
                "machine": machine_id,
                "ncpath": ncpath
            }

            self.redis_tracker.enqueue_job(machine_id, filename, project_id)

            async with httpx.AsyncClient(verify=False) as client:
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
        except Exception:
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
                logging.info(f"📦 Response JSON: {data}")
                program_name = data.get("value", [None])[0]
                if not program_name or not isinstance(program_name, str):
                    return ""
                return program_name

        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)



    async def track_all_machines_forever(self):
        tracked_machines = set()
        while True:
            machines = await self.get_machine_list()
            machine_ids = [m.id for m in machines.machines]

            logger.info(f"📡 Found {len(machine_ids)} machines: {machine_ids}")

            for machine_id in machine_ids:
                if machine_id not in tracked_machines:
                    tracked_machines.add(machine_id)
                    logger.info(f"🛰️ Starting tracking for machine {machine_id}")
                    asyncio.create_task(self._track_single_machine(machine_id))

            await asyncio.sleep(10)


    async def _track_single_machine(self, machine_id: int):
        while True:
            try:
                status = await self.get_machine_status(machine_id)
                logger.info(f"🔍 Machine {machine_id} status = {status.programMode}")

                if status.programMode == 3:
                    queue_data = self.redis_tracker.peek_job(machine_id)
                    logger.info(f"📦 Peeked queue for machine {machine_id}: {queue_data}")
                    
                    if queue_data:
                        filename, project_id = queue_data
                        program_name = await self.get_current_program_name(machine_id)
                        logger.info(f"🎯 Machine {machine_id} current program = {program_name}, queue filename = {filename}")

                        if program_name == filename:
                            self.redis_tracker.mark_processing(project_id, filename, machine_id)
                            logger.info(f"✅ Processing started: {filename} on machine {machine_id}")
                        else:
                            self.redis_tracker.mark_finished(project_id, filename, machine_id)
                            self.redis_tracker.pop_job(machine_id)
                            logger.info(f"🏁 Finished: {filename} on machine {machine_id}")
            except Exception as e:
                logger.error(f"❌ Error tracking machine {machine_id}: {e}", exc_info=True)

            await asyncio.sleep(3)



    async def _monitor_machine_state(self, project_id: str, machine_id: int):
        mode = 0
        current_tool = None
        operation_index = 1
        product_uuid = str(uuid.uuid4())

        log_doc = {
            "project_id": project_id,
            "machine_id": machine_id,
            "product_uuid": product_uuid,
            "start_time": datetime.now(),
            "finish_time": None,
            "finished": False,
            "operations": []
        }

        while True:
            status = await self.get_machine_status(machine_id)

            if status.programMode == 1 and mode != 3:
                mode = 3
                current_tool = await self._get_active_tool_number(machine_id)
                await self._log_product_operation(log_doc, operation_index, current_tool, "start")

            elif status.programMode == 1 and mode == 3:
                tool = await self._get_active_tool_number(machine_id)
                if tool != current_tool:
                    await self._log_product_operation(log_doc, operation_index, current_tool, "end")
                    operation_index += 1
                    await self._log_product_operation(log_doc, operation_index, tool, "start")
                    current_tool = tool

            elif status.programMode != 1 and mode == 3:
                await self._log_product_operation(log_doc, operation_index, current_tool, "end")
                log_doc["finish_time"] = datetime.now()
                log_doc["finished"] = True
                await self.product_log_collection.insert_one(log_doc)
                break

            await asyncio.sleep(1)

    async def _log_product_operation(self, log_doc: dict, index: int, tool_number: int, action: str):
        if action == "start":
            operation = {
                "uuid": str(uuid.uuid4()),
                "index": index,
                "toolNumber": tool_number,
                "start_time": datetime.now(),
                "end_time": None
            }
            log_doc["operations"].append(operation)

        elif action == "end":
            for op in reversed(log_doc["operations"]):
                if op["index"] == index and op["end_time"] is None:
                    op["end_time"] = datetime.now()
                    break
    
    async def _get_active_tool_number(self, machine_id: int, channel: int = 1) -> int:
        try:
            params = {"machine": machine_id, "channel": channel}
            async with httpx.AsyncClient(verify=False) as client:
                res = await client.get(
                    f"{self.gateway_base_url}/machine/channel/activeTool/toolNumber",
                    params=params
                )
                res.raise_for_status()
                data = res.json()
                return int(data.get("value", [0])[0])
        except Exception:
            return -1
