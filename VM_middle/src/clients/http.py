from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional
import httpx


class HttpClient:
    def __init__(self, base_url: str, timeout: float = 15.0, retries: int = 1):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = max(0, retries)

    async def _request(
        self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None
    ) -> httpx.Response:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as cli:
                    resp = await cli.request(method, url, params=params)
                    resp.raise_for_status()
                    return resp
            except Exception as e:
                last_exc = e
                if attempt < self.retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
                else:
                    raise
        assert False, last_exc  # safety

    async def get_json(self, path: str, *, params: Optional[Dict[str, Any]] = None):
        resp = await self._request("GET", path, params=params)
        return resp.json()
