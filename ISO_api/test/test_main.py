import os
import pytest
from fastapi import status
from httpx import AsyncClient, ASGITransport
from src.main import app

BASE_DIR = "/data"
xml_path = os.path.join(BASE_DIR, "xml", "sample.xml")
step_path = os.path.join(BASE_DIR, "step", "DRILLJIG_PLATE_PMI.stp")
nc_path = os.path.join(BASE_DIR, "nc", "O0100")
# tdms_path = os.path.join(BASE_DIR, "tdms", "sample.tdms")
# log_path = os.path.join(BASE_DIR, "tdms", "sample.log")

cam_nx_path = os.path.join(BASE_DIR, "json", "nx", "NX_json.json")
mapping_nx_path = os.path.join(BASE_DIR, "json", "nx", "mapping_config_NX.json")

cam_powermill_path = os.path.join(BASE_DIR, "json", "powermill", "1.json")
mapping_powermill_path = os.path.join(BASE_DIR, "json", "powermill", "mapping_config_constantz.json")

@pytest.mark.asyncio
async def test_full_project_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. 프로젝트 업로드
        project_id = await upload_project(client)

        # 2. STEP 파일 업로드
        step_id, stl_id = await upload_step_file(client, project_id)

        # 3. NC 파일 업로드
        nc_id = await upload_nc_file(client, project_id, "st861")

        # 4. TDMS 로그 업로드 (.txt)
        # await upload_tdms_log(client, project_id, "test_workplan", nc_id)

        # # 5. TDMS 리스트 확인
        # await check_tdms_list(client, project_id, "test_workplan", tdms_path)

        # 6. XML 속성 추출 확인
        await check_xml_attribute(client, project_id, "project")

        # 7. NX 파일 업로드 테스트 (추가)
        await upload_cam_file(client, project_id, cam_nx_path, mapping_nx_path, cam_type="nx")
        
        # 8. Powermill 파일 업로드 테스트 (추가)
        await upload_cam_file(client, project_id, cam_powermill_path, mapping_powermill_path, cam_type="powermill")  # 또는 "PowerMill"로 지정


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
            files={"nc_file": ("O0100", f, "text/plain")}
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
                "tdms_path": "/data/tdms/sample.tdms"
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


async def upload_cam_file(client: AsyncClient, project_id, cam_json_path, mapping_cam_path, cam_type: str):
    """
    CAM 파일 업로드 (NX 또는 PowerMill)
    """
    with open(cam_json_path, "rb") as cam_json, open(mapping_cam_path, "rb") as mapping_json:
        response = await client.post(
            "/api/upload/cam",
            data={
                "project_id": project_id,
                "cam_type": cam_type,
            },
            files={
                "cam_json": ("sample_cam.json", cam_json, "application/json"),
                "mapping_json": ("sample_mapping.json", mapping_json, "application/json"),
            },
        )
    assert response.status_code == status.HTTP_201_CREATED
