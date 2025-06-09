from pydantic import BaseModel, Field
from typing import List, Optional

class ProjectSearchFilter(BaseModel):
    name: Optional[str] = Field(None, description="프로젝트 이름")
    project_id: Optional[str] = Field(None, description="프로젝트 ID")
    page: int = Field(1, ge=0, description="페이지네이션")
    limit: int = Field(10, ge=1, le=100, description="가져올 최대 개수")
    
    
class ProjectOut(BaseModel):
    id: str = Field(...)
    name: str

class ProjectListResponse(BaseModel):
    projects: List[ProjectOut]
    page: int = Field(..., ge=1)
    limit: int = Field(..., ge=1)
    total: int = Field(..., ge=0)
    
class WorkplanNC(BaseModel):
    workplan_id: str
    nc_code_id: Optional[str]

class WorkplanNCResponse(BaseModel):
    results: List[WorkplanNC]

class NcCodeUpdateRequest(BaseModel):
    content: str
    
class NCCodeResponse(BaseModel):
    content: str