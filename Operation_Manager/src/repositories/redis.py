import redis
from datetime import datetime
from typing import Optional, Dict

class RedisRepository:
    """
    Redis를 통한 장비/프로젝트별 NC 파일 상태 관리 기능 제공.
    """
    def __init__(self, host, port):
        self.redis_client = redis.Redis(host=host, port=port, decode_responses=True)

    def initialize_project_cache(self, project_id: str, nc_file_list: list[str]):
        """
        프로젝트별 NC 파일 상태를 '등록' 상태로 초기화
        """
        for filename in nc_file_list:
            existing_keys = self.redis_client.keys(f"status:{project_id}:{filename}:*")
            if not existing_keys:
                status_key = f"status:{project_id}:{filename}:unassigned"
                self.redis_client.hset(status_key, mapping={
                    "status": "등록",
                    "upload_time": ""
                })

    def set_status(self, project_id: str, filename: str, machine_id: int, status: str):
        """
        프로젝트/파일/장비별 상태(key)와 최근 상태값 및 시간 기록
        """
        status_key = f"status:{project_id}:{filename}:{machine_id}"
        self.redis_client.hset(status_key, mapping={
            "status": status,
            "upload_time": datetime.now().isoformat()
        })

    def mark_processing(self, project_id: str, filename: str, machine_id: int):
        """
        특정 파일의 상태를 '가공 중'으로 변경
        """
        self.set_status(project_id, filename, machine_id, "가공 중")

    def mark_finished(self, project_id: str, filename: str, machine_id: int):
        """
        특정 파일의 상태를 '가공 완료'로 변경
        """
        self.set_status(project_id, filename, machine_id, "가공 완료")

    def get_all_statuses(self, project_id: str) -> Dict[str, Dict[str, dict]]:
        """
        프로젝트별 전체 NC 파일 상태 조회 (파일별, 장비별)
        """
        pattern = f"status:{project_id}:*"
        keys = self.redis_client.keys(pattern)
        result = {}
        for key in keys:
            *_, filename, machine_id = key.split(":")
            entry = self.redis_client.hgetall(key)
            if filename not in result:
                result[filename] = {}
            result[filename][machine_id] = entry
        return result

    def find_project_id_by_filename(self, filename: str, machine_id: int):
        """
        실행 중인 파일명 기준으로 project_id 추출
        Redis 키 형식: status:{project_id}:{filename}:{machine_id}
        """
        pattern = f"status:*:{filename}:*"
        keys = self.redis_client.keys(pattern)

        for key in keys:
            parts = key.split(":")
            if len(parts) == 4 and parts[2] == filename and parts[3] == str(machine_id):
                return parts[1]  # project_id
        return None
