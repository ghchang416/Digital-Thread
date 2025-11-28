from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field


class ProjectRow(BaseModel):
    """
    ISO 프로젝트 리스트의 한 줄.
    - gid: Global Asset ID (URL 문자열)
    - aid: ISO Asset ID (dt_project가 속한 asset_id)
    - eid: dt_project의 element_id
    - name: 표시용 이름(응답원본의 display_name/name 등 매핑)
    - description: element_description 등에서 가져온 설명
    - main_wpid: main_workplan 의 its_id
    - wpid: 이 프로젝트가 가지고 있는 workplan its_id 목록 (메인 + 자식/형제)
    - type: 원본 응답에 있으면 보존(선택)
    """

    gid: str = Field(..., min_length=1, description="Global Asset ID (URL string)")
    aid: str = Field(..., min_length=1, description="Asset ID")
    eid: str = Field(..., min_length=1, description="Project element_id")

    name: Optional[str] = Field(None, description="Display name")
    description: Optional[str] = Field(None, description="Project description")

    main_wpid: Optional[str] = Field(
        None,
        description="main_workplan its_id (없을 수 있음)",
    )
    wpid: List[str] = Field(
        default_factory=list,
        description="이 프로젝트가 가지는 workplan its_id 목록",
    )

    type: Optional[str] = Field(None, description="Original item type")


class ProjectListResp(BaseModel):
    items: List[ProjectRow]
    has_more: Optional[bool] = None
    next_offset: Optional[int] = None
    total: Optional[int] = None
