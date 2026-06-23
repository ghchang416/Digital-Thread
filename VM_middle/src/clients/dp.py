# src/clients/dp.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import httpx
from src.core.config import settings


def _dp_headers() -> Dict[str, str]:
    return {
        "accept": "*/*",
        "Authorization": settings.DP_API_KEY,
    }


def _base() -> str:
    return str(settings.DP_API_URL).rstrip("/")


def _raise_for_status_with_detail(
    response: httpx.Response,
    *,
    context: str,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        body = (response.text or "").strip()
        if len(body) > 1000:
            body = body[:1000] + "...(truncated)"
        meta_text = ""
        if meta:
            pairs = [f"{k}={v}" for k, v in meta.items() if v is not None]
            meta_text = f" meta=({', '.join(pairs)})" if pairs else ""
        message = (
            f"{context}: status={response.status_code} "
            f"url='{response.url}'{meta_text} body='{body}'"
        )
        raise httpx.HTTPStatusError(
            message,
            request=exc.request,
            response=exc.response,
        ) from exc


async def list_projects(
    *,
    page: int = 0,
    size: int = 20,
    all_search: Optional[str] = None,
) -> Dict[str, Any]:
    """
    GET /openapi/v2/asset/find/element?type=project&page={page}&size={size}
    반환: { typeCounts, content[], pageable, totalElements, totalPages, ... }
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        params: Dict[str, Any] = {"type": "project", "page": page, "size": size}
        if all_search:
            params["allSearch"] = all_search

        r = await client.get(
            f"{_base()}/openapi/v2/asset/find/element",
            params=params,
            headers=_dp_headers(),
        )
        r.raise_for_status()
        return r.json()


async def list_elements_by_gid(
    gid: str, *, page: int = 0, size: int = 200
) -> Dict[str, Any]:
    """
    GET /openapi/v2/asset/find/element?gid={gid}&page={page}&size={size}
    반환: { typeCounts, content[], ... }
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{_base()}/openapi/v2/asset/find/element",
            params={"gid": gid, "page": page, "size": size},
            headers=_dp_headers(),
        )
        r.raise_for_status()
        return r.json()


async def get_element(aid: str, eid: str) -> Dict[str, Any]:
    """
    GET /openapi/v2/asset/element?aid={aid}&eid={eid}
    반환: { assetGlobalId, assetId, elementId, xmlStr, path, reflist, ... }
    xmlStr에 ISO 14649 XML 전문이 담겨 있음.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{_base()}/openapi/v2/asset/element",
            params={"aid": aid, "eid": eid},
            headers=_dp_headers(),
        )
        r.raise_for_status()
        return r.json()


async def get_element_xml(aid: str, eid: str) -> Optional[str]:
    """
    get_element() 에서 xmlStr 만 추출하여 반환.
    xmlStr이 없거나 빈값이면 None.
    """
    data = await get_element(aid, eid)
    xml = data.get("xmlStr") or ""
    return xml if xml.strip() else None


async def upload_xml(xml_str: str) -> Any:
    """
    POST /openapi/v2/asset/xml
    파일 첨부 없이 XML만 업로드할 때 사용 (upload_result=False 케이스).
    consumes: application/xml → body에 XML 문자열 raw 전송, validation은 query param.
    """
    headers = {**_dp_headers(), "Content-Type": "application/xml"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{_base()}/openapi/v2/asset/xml",
            headers=headers,
            params={"validation": "false"},
            content=xml_str.encode("utf-8"),
        )
        _raise_for_status_with_detail(r, context="DP xml upload failed")
        try:
            return r.json()
        except Exception:
            return r.text


async def upload_xml_with_file(
    xml_str: str,
    *,
    file_path: Optional[str] = None,
    file_name: str = "vm_result.zip",
    content_type: str = "application/zip",
) -> Any:
    """
    POST /openapi/v2/asset/xml-with-file
    multipart/form-data:
      - xmlData : XML 문자열 (<path> 비워서 전송 → DP가 저장 후 자동 채움)
      - files   : VM 결과 파일 (file_path 에서 스트리밍으로 읽어 전송)
      - validation: false
    파일은 전체를 메모리에 올리지 않고 파일 핸들로 스트리밍 전송한다.
    """
    data = {"xmlData": xml_str, "validation": "false"}

    async with httpx.AsyncClient(timeout=600.0) as client:
        if file_path is not None:
            with open(file_path, "rb") as fh:
                r = await client.post(
                    f"{_base()}/openapi/v2/asset/xml-with-file",
                    headers=_dp_headers(),
                    data=data,
                    files=[("files", (file_name, fh, content_type))],
                )
        else:
            r = await client.post(
                f"{_base()}/openapi/v2/asset/xml-with-file",
                headers=_dp_headers(),
                data=data,
            )
        _raise_for_status_with_detail(
            r,
            context="DP xml-with-file upload failed",
            meta={"file_name": file_name, "content_type": content_type},
        )
        try:
            return r.json()
        except Exception:
            return r.text


async def download_nc_file(path: str) -> str:
    """
    GET /openapi/v2/files/download/userdata?path={path}
    path: element 응답의 'path' 필드 값 (예: /userdata/3/nccode1.txt)
    반환: NC 텍스트
    """
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.get(
            f"{_base()}/openapi/v2/files/download/userdata",
            params={"path": path},
            headers=_dp_headers(),
        )
        r.raise_for_status()
        try:
            return r.text
        except Exception:
            return r.content.decode("utf-8", errors="ignore")


async def download_user_file_bytes(path: str) -> tuple[bytes, Optional[str]]:
    """
    GET /openapi/v2/files/download/userdata?path={path}
    path: element 응답의 'path' 필드 값
    반환: (파일 bytes, response content-type)

    NC 텍스트 다운로드 흐름은 건드리지 않기 위해 이미지/바이너리용 별도 함수로 둔다.
    """
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.get(
            f"{_base()}/openapi/v2/files/download/userdata",
            params={"path": path},
            headers=_dp_headers(),
        )
        r.raise_for_status()
        return r.content, r.headers.get("content-type")
