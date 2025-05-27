from pydantic import BaseModel, Field
from typing import List, Optional

class ProjectSearchFilter(BaseModel):
    name: Optional[str] = Field(None, description="프로젝트 이름")
    project_id: Optional[str] = Field(None, description="프로젝트 ID")
    page: int = Field(1, ge=0, description="페이지네이션")
    limit: int = Field(10, ge=1, le=100, description="가져올 최대 개수")
    
    
class ProjectOut(BaseModel):
    id: str = Field(..., alias="_id")
    name: str

    class Config:
        allow_population_by_field_name = True  # _id → id 변환 허용
        arbitrary_types_allowed = True         # Any 필드 타입 허용

class ProjectListResponse(BaseModel):
    projects: List[ProjectOut]
    page: int = Field(..., ge=1)
    limit: int = Field(..., ge=1)
    total: int = Field(..., ge=0)