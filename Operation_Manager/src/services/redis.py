import redis
from datetime import datetime
from typing import Optional, Tuple, List

class RedisJobTracker:
    def __init__(self):
        self.redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)
        
    def initialize_project_cache(self, project_id: str, nc_file_list: List[str]):
        for filename in nc_file_list:
            key = f"status:{project_id}:{filename}"
            if not self.redis_client.exists(key):
                self.redis_client.hset(key, mapping={
                    "machine_id": "",
                    "status": "등록됨",
                    "upload_time": ""
                })

    def enqueue_job(self, machine_id: int, filename: str, project_id: str):
        status_key = f"status:{project_id}:{filename}"
        queue_key = f"queue:{machine_id}"

        self.redis_client.hset(status_key, mapping={
            "machine_id": str(machine_id),
            "status": "가공 대기",
            "upload_time": datetime.now().isoformat()
        })
        self.redis_client.rpush(queue_key, f"{filename}|{project_id}")

    def peek_job(self, machine_id: int) -> Optional[Tuple[str, str]]:
        queue_key = f"queue:{machine_id}"
        raw = self.redis_client.lindex(queue_key, 0)
        if raw:
            parts = raw.split("|")
            if len(parts) == 2:
                return parts[0], parts[1]
        return None

    def pop_job(self, machine_id: int):
        queue_key = f"queue:{machine_id}"
        self.redis_client.lpop(queue_key)

    def mark_processing(self, project_id: str, filename: str):
        status_key = f"status:{project_id}:{filename}"
        self.redis_client.hset(status_key, "status", "가공 중")

    def mark_finished(self, project_id: str, filename: str):
        status_key = f"status:{project_id}:{filename}"
        self.redis_client.hset(status_key, "status", "가공 완료")

    def get_status(self, project_id: str, filename: str) -> str:
        status_key = f"status:{project_id}:{filename}"
        return self.redis_client.hget(status_key, "status") or "알 수 없음"

    def get_machine_id(self, project_id: str, filename: str) -> str:
        status_key = f"status:{project_id}:{filename}"
        return self.redis_client.hget(status_key, "machine_id") or "알 수 없음"

    def get_all_statuses(self, project_id: str) -> dict:
        pattern = f"status:{project_id}:*"
        keys = self.redis_client.keys(pattern)
        statuses = {}
        for key in keys:
            fname = key.split(":")[-1]
            status = self.redis_client.hget(key, "status") or "알 수 없음"
            machine_id = self.redis_client.hget(key, "machine_id") or "알 수 없음"
            statuses[fname] = {
                "status": status,
                "machine_id": machine_id
            }
        return {"statuses": statuses}
