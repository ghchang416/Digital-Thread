from pydantic import BaseModel
from typing import List

class MachineInfo(BaseModel):
    id: int
    name: str
    venderCode: str
    ip_address: str
    toolSystem: float

class MachineListResponse(BaseModel):
    machines: List[MachineInfo]

class MachineProgramStatusResponse(BaseModel):
    programMode: int

from pydantic import BaseModel

class MachineFileUploadResponse(BaseModel):
    status: int   
    filename: str        
    machine_id: int     
    ncpath: str        