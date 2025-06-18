import asyncio
from datetime import datetime
import os
import re
import uuid
import httpx
from src.services.redis import RedisJobTracker
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
    gateway_base_url = os.getenv("TORUS_GATEWAY_URL", "http://10.10.10.49:5001")
    
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
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                root_path = data.get("value", "")[0]
                logging.info(root_path)
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
                status = raw_data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                machine_list = raw_data.get("value", [])
                return MachineListResponse(machines=machine_list)
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)


    async def upload_torus_file(self, project_id: str, machine_id: int, file_id: str) -> MachineFileUploadResponse:
        try:
            byte_io, filename = await self.repository.get_file_byteio_and_name(file_id)
            file_data = byte_io.read()
            ncpath_root = await self._get_nc_root_path(machine_id)
            project_folder_path = f"{ncpath_root}{project_id}/"

            machines = await self.get_machine_list()
            matched_machine = next((m for m in machines.machines if m.id == machine_id), None)
            if not matched_machine:
                raise CustomException(ExceptionEnum.MACHINE_NOT_FOUND)

            if matched_machine.vendorCode.lower() == "fanuc":
                content_str = file_data.decode(errors="ignore")
                o_match = re.search(r"\bO(\d+)", content_str)
                if not o_match:
                    raise CustomException(ExceptionEnum.INVALID_SIMENSE_FORMAT)
                o_number = f"O{o_match.group(1)}"
                if not filename.startswith(o_number):
                    raise CustomException(ExceptionEnum.INVALID_FILE_NAME_FORMAT)

            # ✅ 1. 폴더 존재 확인 → 없으면 생성
            folder_exists = await self._check_folder_exists(machine_id, project_folder_path)
            if not folder_exists:
                await self._create_folder(machine_id, project_folder_path)

            # ✅ 2. 파일 이름 중복 시 삭제
            file_list = await self.get_file_list(machine_id, project_folder_path)
            if filename in file_list:
                await self.delete_file(machine_id, project_folder_path + filename)

            # ✅ 3. 파일 업로드
            files = {
                "file": (filename, file_data, "application/octet-stream")
            }
            params = {
                "machine": machine_id,
                "ncpath": project_folder_path
            }

            self.redis_tracker._set_status(project_id, filename, machine_id, "등록")

            async with httpx.AsyncClient(verify=False) as client:
                response = await client.put(
                    f"{self.gateway_base_url}/file/machine/ncpath",
                    files=files,
                    params=params
                )
                response.raise_for_status()
                result = response.json()
                if result.get("status", 0) != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

                return MachineFileUploadResponse(
                    status=result.get("status", -1),
                    filename=filename,
                    machine_id=machine_id,
                    ncpath=project_folder_path
                )
        except CustomException as ce:
            logging.info(ce)
            raise ce
        except Exception as e:
            logging.info(e)
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
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                program_mode = data.get("value", [None])[0]
                return MachineProgramStatusResponse(programMode=program_mode)
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
        
    async def delete_file(self, machine_id: int, ncpath: str):
        try:
            params = {'machine': machine_id, 'ncpath': ncpath}
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.delete(
                    f"{self.gateway_base_url}/file/machine/ncpath/delete",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                result = data.get("value", [None])[0]
                return
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR) 
        
    async def get_current_program_name(self, machine_id: int) -> str:
        try:
            params = {'machine': machine_id, 'channel': 1}
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.gateway_base_url}/machine/channel/currentProgram/currentFile/programNameWithPath",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                program_name = data.get("value", [None])[0]
                if not program_name or not isinstance(program_name, str):
                    return ""
                return program_name

        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def get_file_list(self, machine_id: int, ncpath: str):
        try:
            params = {'machine': machine_id, 'ncpath': ncpath}
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.gateway_base_url}/file/machine/ncpath/list",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                result = data.get("files", [None])
                return result

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
        current_tool = None
        operation_index = 1
        product_uuid = str(uuid.uuid4())
        log_doc = None
        is_processing = False
        current_project_id = None
        current_filename = None

        while True:
            try:
                status = await self.get_machine_status(machine_id)
                logger.info(f"🔍 Machine {machine_id} status = {status.programMode}")

                if status.programMode == 3:  # 가공 중
                    program_path = await self.get_current_program_name(machine_id)
                    dir_path = os.path.dirname(program_path)
                    program_name = os.path.basename(program_path)

                    if dir_path == "//CNC_MEM/USER/LIBRARY":
                        await asyncio.sleep(3)
                        continue

                    # 캐시에서 해당 파일과 프로젝트 정보 확인
                    project_id = self.redis_tracker.find_project_id_by_filename(program_name)
                    if not project_id:
                        logger.warning(f"⚠️ No project found for {program_name} on machine {machine_id}")
                        await asyncio.sleep(3)
                        continue

                    self.redis_tracker.mark_processing(project_id, program_name, machine_id)
                    logger.info(f"✅ Processing: {program_name} on machine {machine_id}")

                    tool = await self._get_active_tool_number(machine_id)

                    if not is_processing:
                        # 최초 가공 시작
                        is_processing = True
                        current_tool = tool
                        current_project_id = project_id
                        current_filename = program_name
                        log_doc = {
                            "project_id": project_id,
                            "machine_id": machine_id,
                            "product_uuid": product_uuid,
                            "start_time": datetime.now(),
                            "finish_time": None,
                            "finished": False,
                            "operations": []
                        }
                        await self._log_product_operation(log_doc, operation_index, current_tool, "start")
                    elif tool != current_tool:
                        # 툴 변경
                        await self._log_product_operation(log_doc, operation_index, current_tool, "end")
                        operation_index += 1
                        await self._log_product_operation(log_doc, operation_index, tool, "start")
                        current_tool = tool

                elif is_processing:
                    # 가공 종료 감지
                    self.redis_tracker.mark_finished(current_project_id, current_filename, machine_id)
                    logger.info(f"🏁 Finished: {current_filename} on machine {machine_id}")
                    await self._log_product_operation(log_doc, operation_index, current_tool, "end")
                    log_doc["finish_time"] = datetime.now()
                    log_doc["finished"] = True
                    await self.product_log_collection.insert_one(log_doc)
                    # 상태 초기화
                    product_uuid = str(uuid.uuid4())
                    is_processing = False
                    log_doc = None
                    current_project_id = None
                    current_filename = None

            except Exception as e:
                logger.error(f"❌ Error tracking machine {machine_id}: {e}", exc_info=True)

            await asyncio.sleep(3)

    async def _check_folder_exists(self, machine_id: int, path: str) -> bool:
        try:
            params = {
                "machine": machine_id,
                "path": path  # 폴더 확인 시 반드시 '/' 끝에 붙여야 폴더로 인식됨
            }
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(f"{self.gateway_base_url}/file/exists", params=params)
                response.raise_for_status()
                result = response.json()
                return result.get("exists", False)
        except Exception as e:
            logging.warning(f"check_folder_exists 실패: {e}")
            return False

    async def _create_folder(self, machine_id: int, path: str) -> None:
        try:
            payload = {
                "machine": machine_id,
                "ncpath": path
            }
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(f"{self.gateway_base_url}/file/machine/createfolder", json=payload)
                response.raise_for_status()
                result = response.json()
                if result.get("status", -1) != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
        except Exception as e:
            logging.warning(f"create_folder 실패: {e}")
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)


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
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                return int(data.get("value", [0])[0])
        except Exception:
            return -1
        
