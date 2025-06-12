import redis
from datetime import datetime
from typing import Optional, Tuple, List

class RedisJobTracker:
    def __init__(self):
        self.redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)
    
    def initialize_project_cache(self, project_id: str, nc_file_list: list[str]):
        for filename in nc_file_list:
            existing_keys = self.redis_client.keys(f"status:{project_id}:{filename}:*")
            if not existing_keys:
                status_key = f"status:{project_id}:{filename}:unassigned"
                self.redis_client.hset(status_key, mapping={
                    "status": "등록",
                    "upload_time": ""
                })

    def enqueue_job(self, machine_id: int, filename: str, project_id: str):
        queue_key = f"queue:{machine_id}"
        self.redis_client.rpush(queue_key, f"{filename}|{project_id}")
        self._set_status(project_id, filename, machine_id, "가공 대기")

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

    def peek_job(self, machine_id: int) -> Optional[Tuple[str, str]]:
        queue_key = f"queue:{machine_id}"
        raw = self.redis_client.lindex(queue_key, 0)
        return tuple(raw.split("|")) if raw and "|" in raw else None

    def pop_job(self, machine_id: int):
        queue_key = f"queue:{machine_id}"
        self.redis_client.lpop(queue_key)

    def get_all_statuses(self, project_id: str) -> dict:
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
