import httpx
import logging
from src.utils.exceptions import CustomException, ExceptionEnum

class MachineRepository:
    """
    Torus Gateway API와 통신하여 CNC 장비의 정보, NC 파일 관리, 상태 조회 등의 기능을 제공하는 리포지토리.
    """

    def __init__(self, base_url: str):
        """
        :param base_url: Torus Gateway API의 기본 URL (ex: http://host.docker.internal:5001)
        """
        self.base_url = base_url

    async def get_machine_list(self):
        """
        모든 CNC 장비의 목록을 Torus Gateway에서 조회.
        :raises CustomException: 외부 API 호출 실패 또는 상태 코드 이상시
        :return: 장비 정보 리스트(dict)
        """
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
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))

    async def get_data(self, endpoint: str, params: dict = None):
        """
        주어진 endpoint 경로로 GET 요청을 전송하여 데이터를 반환합니다.
        
        :param endpoint: base_url 뒤에 붙는 API 경로 (예: '/machine/list')
        :param params: 요청 파라미터 (dict)
        :raises CustomException: API 호출 실패 또는 상태 오류 시
        :return: 응답 데이터의 value 필드 또는 전체 json
        """
        try:
            url = f"{self.base_url}{endpoint}"
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                status = data.get("status", 0)
                if status != 0:
                    raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
                return data.get("value", data)
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))


    async def get_nc_root_path(self, machine_id: int):
        """
        지정한 장비의 NC 파일 최상위 루트 경로 반환.
        :param machine_id: 장비 ID
        :raises CustomException: 외부 API 호출 실패 또는 상태 코드 이상시
        :return: NC 루트 경로 (str)
        """
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
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))

    async def ensure_folder_exists(self, machine_id: int, path: str):
        """
        지정한 장비 내 경로의 폴더가 없으면 생성.
        :param machine_id: 장비 ID
        :param path: 폴더 경로
        :raises CustomException: 폴더 생성 실패시
        """
        try:
            params = {
                "machine": machine_id,
                "ncpath": path
            }
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(f"{self.base_url}/file/machine/ncpath/exists", params=params)
                response.raise_for_status()
                result = response.json()
                exists = result.get("value", [False])[0]
                if not exists:
                    payload = {
                        "machine": machine_id,
                        "ncpath": path[:-1]
                    }
                    create_response = await client.post(
                        f"{self.base_url}/file/machine/ncpath/mkdir", json=payload
                    )
                    create_response.raise_for_status()
                    create_result = create_response.json()
                    if create_result.get("status", -1) != 0:
                        raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR)
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))

    async def remove_file_if_exists(self, machine_id: int, path: str, filename: str):
        """
        지정한 경로에 동일한 파일명이 있을 경우 삭제.
        :param machine_id: 장비 ID
        :param path: NC 경로
        :param filename: NC 파일명
        :raises CustomException: 삭제 실패시
        """
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
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))

    async def put_nc_file(self, machine_id: int, path: str, filename: str, data: bytes):
        """
        NC 파일을 CNC 장비로 업로드.
        :param machine_id: 장비 ID
        :param path: 업로드 경로
        :param filename: 파일 이름
        :param data: 바이너리 데이터
        :raises CustomException: 업로드 실패시
        """
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
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))

    async def get_machine_status(self, machine_id: int):
        """
        장비의 현재 프로그램 가공 모드(programMode) 반환.
        :param machine_id: 장비 ID
        :raises CustomException: API 오류시
        :return: int 또는 None (예: 3:가공중, 1:대기)
        """
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
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))

    async def get_current_program_name(self, machine_id: int):
        """
        장비의 현재 프로그램(파일) 이름(경로 포함) 반환.
        :param machine_id: 장비 ID
        :raises CustomException: API 오류시
        :return: 파일명 (str)
        """
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
        except Exception as e:
            raise CustomException(ExceptionEnum.EXTERNAL_REQUEST_ERROR, detail=str(e))

    async def get_active_tool_number(self, machine_id: int):
        """
        장비의 현재 활성화된 공구 번호를 반환.
        :param machine_id: 장비 ID
        :return: 공구 번호 (int) / 실패시 -1
        """
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
            return -1  # API 오류 발생 시 -1 반환
