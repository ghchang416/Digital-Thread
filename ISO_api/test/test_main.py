import os
import pytest
from fastapi import status
from httpx import AsyncClient, ASGITransport
from src.main import app

BASE_DIR = "/data"
xml_path = os.path.join(BASE_DIR, "xml", "sample.xml")
step_path = os.path.join(BASE_DIR, "step", "sample.stp")
nc_path = os.path.join(BASE_DIR, "nc", "O2002.nc")
# tdms_path = os.path.join(BASE_DIR, "tdms", "01__O6025__YPH 025-MAIN P_G__250113114429.tdms")
# log_path = os.path.join(BASE_DIR, "tdms", "01__O6025__YPH 025-MAIN P_G__250112111811_ext.log")


@pytest.mark.asyncio
async def test_full_project_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. 프로젝트 업로드
        project_id = await upload_project(client)

        # 2. STEP 파일 업로드
        step_id, stl_id = await upload_step_file(client, project_id)

        # 3. NC 파일 업로드
        nc_id = await upload_nc_file(client, project_id, "test_workplan")

        # # 4. TDMS 로그 업로드 (.txt)
        # await upload_tdms_log(client, project_id, "test_workplan", nc_id)

        # # 5. TDMS 리스트 확인
        # await check_tdms_list(client, project_id, "test_workplan", tdms_path)

        # # 6. XML 속성 추출 확인
        # await check_xml_attribute(client, project_id, "project")


async def upload_project(client: AsyncClient):
    with open(xml_path, "rb") as f:
        response = await client.post(
            "/api/projects/",
            files={"project_xml_file": ("sample.xml", f, "application/xml")}
        )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()["project_id"]


async def upload_step_file(client: AsyncClient, project_id):
    with open(step_path, "rb") as f:
        response = await client.post(
            "/api/upload/stp",
            data={"project_id": project_id},
            files={"step_file": ("sample.STEP", f, "application/octet-stream")}
        )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    return body["step_id"], body["stl_id"]


async def upload_nc_file(client: AsyncClient, project_id, workplan_id):
    with open(nc_path, "rb") as f:
        response = await client.post(
            "/api/upload/nc",
            data={"project_id": project_id, "workplan_id": workplan_id},
            files={"nc_file": ("O2002.nc", f, "text/plain")}
        )
    assert response.status_code == status.HTTP_201_CREATED
    return response.json()["file_id"]


async def upload_tdms_log(client: AsyncClient, project_id, workplan_id, nc_code_id):
    with open(log_path, "rb") as f:
        response = await client.post(
            "/api/upload/tdms",
            data={
                "project_id": project_id,
                "workplan_id": workplan_id,
                "nc_code_id": nc_code_id,
                "tdms_path": "/data/tdms/01__O6025__YPH 025-MAIN P_G__250113114429.tdms"
            },
            files={"log_file": ("sample.log", f, "text/plain")}
        )
    assert response.status_code == status.HTTP_201_CREATED


async def check_tdms_list(client: AsyncClient, project_id, workplan_id, tdms_path):
    response = await client.get(f"/api/projects/{workplan_id}/tdms_list/?project_id={project_id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert "tdms_list" in data
    assert len(data["tdms_list"]) == 1
    assert data['tdms_list'][0] == tdms_path


async def check_xml_attribute(client: AsyncClient, project_id, attribute_path):
    response = await client.get(
        f"/api/projects/extract/{attribute_path}?project_id={project_id}"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"] == "application/xml"
