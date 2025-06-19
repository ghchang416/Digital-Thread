import httpx
from src.utils.exceptions import CustomException, ExceptionEnum

class MachineRepository:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def get_machine_list(self):
        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(f"{self.base_url}/machine/list")
                response.raise_for_status()
                raw_data = response.json()
                status = raw_data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                return raw_data.get("value", [])
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def get_nc_root_path(self, machine_id: int):
        try:
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.base_url}/machine/ncMemory/rootPath",
                    params={"machine": machine_id}
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                return data.get("value", [""])[0]
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def get_machine_info(self, machine_id: int):
        # machine_id로 개별 장비 정보 반환
        machines = await self.get_machine_list()
        return next((m for m in machines if m['id'] == machine_id), None)

    async def ensure_folder_exists(self, machine_id: int, path: str):
        try:
            params = {
                "machine": machine_id,
                "path": path
            }
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(f"{self.base_url}/file/exists", params=params)
                response.raise_for_status()
                result = response.json()
                exists = result.get("exists", False)
                if not exists:
                    payload = {
                        "machine": machine_id,
                        "ncpath": path
                    }
                    create_response = await client.post(
                        f"{self.base_url}/file/machine/createfolder", json=payload
                    )
                    create_response.raise_for_status()
                    create_result = create_response.json()
                    if create_result.get("status", -1) != 0:
                        raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def remove_file_if_exists(self, machine_id: int, path: str, filename: str):
        try:
            params = {"machine": machine_id, "ncpath": path}
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.base_url}/file/machine/ncpath/list", params=params
                )
                response.raise_for_status()
                data = response.json()
                files = data.get("files", [])
                if filename in files:
                    del_params = {'machine': machine_id, 'ncpath': f"{path}{filename}"}
                    del_response = await client.delete(
                        f"{self.base_url}/file/machine/ncpath/delete", params=del_params
                    )
                    del_response.raise_for_status()
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def put_nc_file(self, machine_id: int, path: str, filename: str, data: bytes):
        try:
            files = {
                "file": (filename, data, "application/octet-stream")
            }
            params = {
                "machine": machine_id,
                "ncpath": path
            }
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.put(
                    f"{self.base_url}/file/machine/ncpath",
                    files=files,
                    params=params
                )
                response.raise_for_status()
                result = response.json()
                if result.get("status", 0) != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def get_machine_status(self, machine_id: int):
        try:
            params = {'machine': machine_id, 'channel': 1}
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.base_url}/machine/channel/currentProgram/programMode",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                return data.get("value", [None])[0]
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def get_current_program_name(self, machine_id: int):
        try:
            params = {'machine': machine_id, 'channel': 1}
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(
                    f"{self.base_url}/machine/channel/currentProgram/currentFile/programNameWithPath",
                    params=params
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                return data.get("value", [None])[0]
        except Exception:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)

    async def get_active_tool_number(self, machine_id: int):
        try:
            params = {"machine": machine_id, "channel": 1}
            async with httpx.AsyncClient(verify=False) as client:
                res = await client.get(
                    f"{self.base_url}/machine/channel/activeTool/toolNumber",
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
