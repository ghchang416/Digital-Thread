import os
import uuid
from datetime import datetime

_log_file_path = None

def generate_uuid():
    return str(uuid.uuid4())

def write_log(message: str):
    global _log_file_path

    if _log_file_path is None:
        now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_dir = os.path.join(os.getcwd(), "log")
        os.makedirs(log_dir, exist_ok=True)
        _log_file_path = os.path.join(log_dir, f"{now}.txt")

        with open(_log_file_path, "w", encoding="utf-8") as f:
            f.write("LOG START\n")

    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(_log_file_path, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} : {message}\n")
