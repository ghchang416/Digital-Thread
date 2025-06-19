import asyncio
from datetime import datetime
import re
import uuid
import logging
from src.repositories import MachineRepository, FileRepository, MachineLogRepository, RedisRepository
from src.schemas.machine import (
    MachineFileUploadResponse, MachineListResponse, MachineProgramStatusResponse, MachineInfo
)
from src.utils.exceptions import CustomException, ExceptionEnum
import logging

class MachineService:
    def __init__(self, machine_repo: MachineRepository, file_repo: FileRepository, log_repo: MachineLogRepository, job_tracker: RedisRepository):
        self.machine_repo = machine_repo
        self.file_repo = file_repo
        self.log_repo = log_repo
        self.job_tracker = job_tracker

    async def get_machine_list(self) -> MachineListResponse:
        raw_list = await self.machine_repo.get_machine_list()
        machines = [MachineInfo(**item) for item in raw_list]
        return MachineListResponse(machines=machines)

    async def upload_torus_file(self, project_id: str, machine_id: int, file_id: str) -> MachineFileUploadResponse:
        # 1. 파일 조회
        byte_io, filename = await self.file_repo.get_file_byteio_and_name(file_id)
        file_data = byte_io.read()
        # 2. NC 루트 경로 조회 및 폴더 생성/중복 삭제 등 외부 API 처리
        ncpath_root = await self.machine_repo.get_nc_root_path(machine_id)
        project_folder_path = f"{ncpath_root}{project_id}/"

        machine_info: MachineListResponse = await self.machine_repo.get_machine_info(machine_id)
        matched_machine = next((m for m in machine_info.machines if m.id == machine_id), None)
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


        await self.machine_repo.ensure_folder_exists(machine_id, project_folder_path)
        await self.machine_repo.remove_file_if_exists(machine_id, project_folder_path, filename)

        # 3. 실제 파일 업로드
        await self.machine_repo.put_nc_file(machine_id, project_folder_path, filename, file_data)
        self.job_tracker.set_status(project_id, filename, machine_id, "등록")

        return MachineFileUploadResponse(
            status=0,
            filename=filename,
            machine_id=machine_id,
            ncpath=project_folder_path
        )

    async def get_machine_status(self, machine_id: int) -> MachineProgramStatusResponse:
        program_mode = await self.machine_repo.get_machine_status(machine_id)
        return MachineProgramStatusResponse(programMode=program_mode)

    async def track_all_machines_forever(self):
        tracked_machines = set()
        while True:
            machines = await self.get_machine_list()
            machine_ids = [m.id for m in machines.machines]

            logging.info(f"📡 Found {len(machine_ids)} machines: {machine_ids}")

            for machine_id in machine_ids:
                if machine_id not in tracked_machines:
                    tracked_machines.add(machine_id)
                    logging.info(f"🛰️ Starting tracking for machine {machine_id}")
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
                logging.info(f"🔍 Machine {machine_id} status = {status.programMode}")

                if status.programMode == 3:  # 가공 중
                    program_name = await self.machine_repo.get_current_program_name(machine_id)
                    project_id = self.job_tracker.find_project_id_by_filename(program_name)
                    if not project_id:
                        logging.warning(f"⚠️ No project found for {program_name} on machine {machine_id}")
                        await asyncio.sleep(3)
                        continue

                    self.job_tracker.mark_processing(project_id, program_name, machine_id)
                    tool = await self.machine_repo.get_active_tool_number(machine_id)

                    if not is_processing:
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
                        await self._log_product_operation(log_doc, operation_index, current_tool, "end")
                        operation_index += 1
                        await self._log_product_operation(log_doc, operation_index, tool, "start")
                        current_tool = tool

                elif is_processing:
                    self.job_tracker.mark_finished(current_project_id, current_filename, machine_id)
                    logging.info(f"🏁 Finished: {current_filename} on machine {machine_id}")
                    await self._log_product_operation(log_doc, operation_index, current_tool, "end")
                    log_doc["finish_time"] = datetime.now()
                    log_doc["finished"] = True
                    await self.log_repo.insert_log(log_doc)
                    # 상태 초기화
                    product_uuid = str(uuid.uuid4())
                    is_processing = False
                    log_doc = None
                    current_project_id = None
                    current_filename = None

            except Exception as e:
                logging.error(f"❌ Error tracking machine {machine_id}: {e}", exc_info=True)
            await asyncio.sleep(3)

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