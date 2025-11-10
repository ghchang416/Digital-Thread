# src/schemas/vm_project.py
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field, field_validator
from typing import Literal, Dict
from enum import Enum

VmProjectStatus = Literal[
    "needs-fix",  # 유효성 오류: VM 호출 불가(수정 필요)
    "ready",  # 유효성 통과: 사용자 VM 호출 대기 상태
    "running",  # VM 호출 후 폴링 중
    "completed",  # VM 완료(성공)
    "failed",  # VM 실패
]


# 2) 런타임 검증 & OpenAPI 문서화를 위한 Enum
class VmProjectStatusEnum(str, Enum):
    needs_fix = "needs-fix"
    ready = "ready"
    running = "running"
    completed = "completed"
    failed = "failed"


# ==== 입력 ====
class VmProjectCreateIn(BaseModel):
    """
    ISO로부터 VM 프로젝트 생성을 위한 키 입력.
    - gid: Global Asset ID (URL)
    - aid: Asset ID
    - eid: 프로젝트 element_id (dt_project)
    - wpid: (선택) workplan its_id
    """

    gid: str = Field(..., min_length=1, description="Global Asset ID (URL)")
    aid: str = Field(..., min_length=1, description="Asset ID")
    eid: str = Field(..., min_length=1, description="Project element_id")
    wpid: Optional[str] = Field(None, description="Workplan its_id (optional)")

    model_config = {"extra": "forbid"}  # 레거시 키나 불필요한 필드 차단


# ==== 공통 하위 구조 ====
class ProcessItemIn(BaseModel):
    file_path: Optional[str] = Field(
        None,
        description="작업에 사용할 NC 파일 경로(작업 디렉토리 기준 상대경로; 미리보기 단계에서는 None)",
    )
    output_dir_path: Optional[str] = Field(
        None,
        description="결과 출력 디렉토리(작업 디렉토리 기준 상대경로; 미리보기 단계에서는 None)",
    )
    tool_data: Optional[str] = Field(
        None,
        description=(
            "툴 정보 CSV (예: 'T,eff_diam,corner_radius,eff/2-corner,...'); "
            "미리보기 단계에서는 None 가능"
        ),
    )


class StockInfo(BaseModel):
    stock_type: Optional[int] = Field(
        None, description="소재 타입 코드(내부 매핑 결과)"
    )
    stock_size: Optional[str] = Field(
        None, description="x0,y0,z0,x1,y1,z1 (6개 실수, 콤마 구분)"
    )
    reason: Optional[str] = Field(None, description="산출/추론 사유")

    @field_validator("stock_size")
    @classmethod
    def _validate_stock_size(cls, v: Optional[str]):
        if v is None:
            return v
        parts = v.split(",")
        if len(parts) != 6:
            raise ValueError(
                "stock_size는 'x0,y0,z0,x1,y1,z1' 형식의 6개 값이어야 합니다."
            )
        for p in parts:
            float(p.strip())
        return v


# ==== 출력 ====
class ProjectFileOut(BaseModel):
    stock_type: Optional[int]
    stock_size: Optional[str]
    process_count: int
    process: List[ProcessItemIn]


class CreateFromIsoOut(BaseModel):
    id: str
    stock: StockInfo
    project_file: ProjectFileOut


class StockPatchIn(BaseModel):
    stock_type: Optional[int] = None
    stock_size: Optional[str] = None

    @field_validator("stock_size")
    @classmethod
    def _validate_stock_size(cls, v: Optional[str]):
        if v is None:
            return v
        parts = v.split(",")
        if len(parts) != 6:
            raise ValueError(
                "stock_size는 'x0,y0,z0,x1,y1,z1' 형식의 6개 값이어야 합니다."
            )
        for p in parts:
            float(p.strip())
        return v


class ProcessPatchIn(BaseModel):
    process: List[ProcessItemIn]


class PreviewFromIsoOut(BaseModel):
    stock: StockInfo
    project_file: ProjectFileOut


class VmProjectListItem(BaseModel):
    id: str
    status: VmProjectStatusEnum = Field(
        description="needs-fix/ready/running/completed/failed"
    )
    proj_name: str | None = None
    gid: str
    aid: str
    eid: str
    wpid: str | None = None
    created_at: str
    updated_at: str
    validation_is_valid: bool | None = None
    validation_error_count: int = 0


class VmProjectListResponse(BaseModel):
    total: int
    page: int
    size: int
    has_more: bool
    items: list[VmProjectListItem]


class VmProjectDetailOut(BaseModel):
    id: str = Field(description="vm_project _id")
    status: VmProjectStatusEnum = Field(description="현재 상태")
    proj_name: Optional[str] = None

    gid: str
    aid: str
    eid: str
    wpid: Optional[str] = None

    created_at: str
    updated_at: str

    # 최신 파일 포인터 (vm_file_id 문자열로 변환)
    latest_files: Dict[str, str] = Field(
        default_factory=dict,
        description="{'nc-split-zip': '<oid>', 'vm-project-json': '<oid>'}",
    )

    # 유효성 결과
    validation_is_valid: Optional[bool] = None
    validation_errors: list[str] = Field(default_factory=list)

    # 초안 프로젝트 파일(실행 전 편집본)
    project_file_draft: ProjectFileOut


class StockItemOut(BaseModel):
    code: int = Field(description="stock_type 코드 (정수)")
    name: str = Field(description="표시용 원문 이름(정확 문자열)")


class StockItemsResponse(BaseModel):
    items: List[StockItemOut]
