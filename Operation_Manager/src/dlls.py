import os
import clr
import requests
from utils import write_log

class Torus:
    def __init__(self):
        self.is_initialized = False
        self.dll_server = "http://localhost:8000"
        
    def _get_int(self, adress_: str, filter_: str, direct_: bool) -> int:
        response = requests.get(f"{self.dll_server}/int", params={"adress_": adress_, "filter_": filter_, "direct_": direct_})
        return response.json().get("value", -1)

    def _get_string(self, adress_: str, filter_: str, direct_: bool) -> str:
        response = requests.get(f"{self.dll_server}/string", params={"adress_": adress_, "filter_": filter_, "direct_": direct_})
        return response.json().get("value", "")


    def get_status(self):
        return self._get_int("data://machine/channel/currentProgram/programMode", "machine=1&channel=1", False)

    def get_program_name(self):
        return self._get_string("data://machine/channel/currentprogram/currentfile/programname", "channel=1", False)


    def upload(self, file_path: str, name: str):
        write_log("UploadFile start : " + name)

        with open(file_path, "rb") as f:
            files = {"file": (name, f, "text/plain")}
            data = {"name": name}
            
            response = requests.post(
                f"{self.dll_server}/upload/file",
                files=files,
                data=data
            )

        if response.status_code != 200:
            raise RuntimeError(f"Upload failed: {response.text}")
        
        write_log("UploadFile start : " + name)
        return response.json()
    
    
    
        
"""
gd&t 기하 공차 dll 서버 wrapping
"""

# BASE_PATH = os.path.abspath("./padirect_ages")
# clr.AddReference(os.path.join(BASE_PATH, "inspectiondata.dll"))
# import inspectiondata

# def run_inspection(project_root: str, project_id: str, product_id: int) -> list:
#     gdt_path = os.path.join(project_root, project_id, "GDNT", "gdnt.nc")
#     result_path = os.path.join(project_root, project_id, "Products", str(product_id), "GDNT", "gdnt.result")

#     result = Array[Double]([0] * 50)
#     instance = inspectiondata.inspectiongdtdata()
#     instance.getinspectiondata(gdt_path, result_path, result)
#     return
