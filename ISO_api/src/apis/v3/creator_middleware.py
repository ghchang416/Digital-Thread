from starlette.responses import JSONResponse

from src.services.creator.els.sessions import UPLOAD_BODY_LIMIT


class ElsUploadTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    def __init__(self, app, limit=2 * 1024 * 1024, path_prefix="/api/v3/creator"):
        self.app, self.limit, self.path_prefix = app, limit, path_prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(self.path_prefix + "/"):
            return await self.app(scope, receive, send)
        if scope["method"] == "POST" and scope["path"] == self.path_prefix + "/els/imports":
            return await self._els_upload(scope, receive, send)
        chunks, size = [], 0
        limit = 32 * 1024 * 1024 if scope["path"] in {self.path_prefix + path for path in ("/cam/parse", "/nc/analyze", "/nc/tools")} else self.limit
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > limit:
                return await JSONResponse({"detail": f"Request body exceeds {limit // (1024 * 1024)} MiB"}, status_code=413)(scope, receive, send)
            chunks.append(message.get("body", b""))
            if not message.get("more_body"):
                break
        consumed = False

        async def replay():
            nonlocal consumed
            if consumed:
                return await receive()
            consumed = True
            return {"type": "http.request", "body": b"".join(chunks), "more_body": False}

        await self.app(scope, replay, send)

    async def _els_upload(self, scope, receive, send):
        # Only ELS upload streams to the multipart parser; all legacy branches stay unchanged.
        size = 0

        async def bounded_receive():
            nonlocal size
            message = await receive()
            if message["type"] == "http.request":
                size += len(message.get("body", b""))
                if size > UPLOAD_BODY_LIMIT:
                    raise ElsUploadTooLarge()
            return message

        try:
            lengths = [value for key, value in scope.get("headers", []) if key == b"content-length"]
            if lengths and (len(lengths) != 1 or not lengths[0].isdigit() or len(lengths[0]) > 12):
                return await JSONResponse({"detail": "INVALID_CONTENT_LENGTH"}, status_code=400)(scope, receive, send)
            if lengths and int(lengths[0]) > UPLOAD_BODY_LIMIT:
                raise ElsUploadTooLarge()
            await self.app(scope, bounded_receive, send)
        except ElsUploadTooLarge:
            await JSONResponse({"detail": "ELS_UPLOAD_BODY_TOO_LARGE"}, status_code=413,
                               headers={"Cache-Control": "no-store"})(scope, receive, send)
