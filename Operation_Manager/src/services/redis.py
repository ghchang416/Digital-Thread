import redis
from datetime import datetime
from typing import Optional, Dict

class RedisJobTracker:
    def __init__(self):
        self.redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

    def initialize_project_cache(self, project_id: str, nc_file_list: list[str]):
        """
        프로젝트별 NC 파일 상태를 등록 상태로 초기화
        """
        for filename in nc_file_list:
            existing_keys = self.redis_client.keys(f"status:{project_id}:{filename}:*")
            if not existing_keys:
                status_key = f"status:{project_id}:{filename}:unassigned"
                self.redis_client.hset(status_key, mapping={
                    "status": "등록",
                    "upload_time": ""
                })

    def _set_status(self, project_id: str, filename: str, machine_id: int, status: str):
        status_key = f"status:{project_id}:{filename}:{machine_id}"
        self.redis_client.hset(status_key, mapping={
            "status": status,
            "upload_time": datetime.now().isoformat()
        })

    def mark_processing(self, project_id: str, filename: str, machine_id: int):
        self._set_status(project_id, filename, machine_id, "가공 중")

    def mark_finished(self, project_id: str, filename: str, machine_id: int):
        self._set_status(project_id, filename, machine_id, "가공 완료")

    def get_all_statuses(self, project_id: str) -> Dict[str, Dict[str, dict]]:
        """
        프로젝트별 전체 파일 상태 확인
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

    def find_project_id_by_filename(self, filename: str) -> Optional[str]:
        """
        현재 실행 중인 파일 이름으로 project_id 검색
        """
        keys = self.redis_client.keys(f"status:*:{filename}:*")
        for key in keys:
            parts = key.split(":")
            if len(parts) >= 3:
                return parts[1]  # project_id
        return None
