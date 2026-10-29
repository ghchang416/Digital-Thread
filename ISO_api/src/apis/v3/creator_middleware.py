from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app, limit=2 * 1024 * 1024, path_prefix="/api/v3/creator"):
        self.app, self.limit, self.path_prefix = app, limit, path_prefix

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(self.path_prefix + "/"):
            return await self.app(scope, receive, send)
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
