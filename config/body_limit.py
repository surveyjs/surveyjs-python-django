"""A cap on request bodies and WebSocket messages, around the whole ASGI application (config/asgi.py).

Django limits a non-file body (DATA_UPLOAD_MAX_MEMORY_SIZE) and the number of files, but not the size of a
multipart body's files, and its ASGI handler reads the whole body before a view runs. 24 MB fits the largest body
this app accepts: a 5 MB scan, base64-encoded for the SurveyJS service, arrives here as multipart, and a Creator
definition with images is a few MB. The views keep their own 5 MB rules. Pure ASGI (from surveyjs-python-fastapi's
app/body_limit.py), so it sees WebSocket connections too.
"""

import json

MAX_BODY = 24 * 1024 * 1024
TOO_LARGE = "The request body is too large"


class BodyLimit:
    def __init__(self, app, max_bytes: int = MAX_BODY) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "websocket":
            return await self.app(scope, self._websocket(receive, send), send)
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and length.isdigit() and int(length) > self.max_bytes:
            return await self._refuse(send)

        received = 0
        refused = False

        async def counted():
            nonlocal received, refused
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:   # a chunked body with no Content-Length: answer, stop reading it
                    refused = True
                    await self._refuse(send)
                    return {"type": "http.disconnect"}
            return message

        async def unless_refused(message) -> None:
            if not refused:
                await send(message)

        await self.app(scope, counted, unless_refused)

    def _websocket(self, receive, send):
        async def limited():
            message = await receive()
            if message["type"] == "websocket.receive":
                size = len(message.get("text") or "") + len(message.get("bytes") or b"")
                if size > self.max_bytes:   # 1009: message too big
                    await send({"type": "websocket.close", "code": 1009})
                    return {"type": "websocket.disconnect", "code": 1009}
            return message
        return limited

    @staticmethod
    async def _refuse(send) -> None:
        body = json.dumps({"error": TOO_LARGE}).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})
