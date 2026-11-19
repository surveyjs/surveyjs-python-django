"""What the tests share: an API client that says who it is on every call, the page config of a rendered page, the
round-trip document, the mocked SurveyJS service, a client for the whole ASGI application, a WebSocket client
for the relays, and reloading the URLconf after a switch changes."""

import importlib
import json
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import httpx2
from asgiref.testing import ApplicationCommunicator
from django.db import connections
from django.test import Client, TransactionTestCase, override_settings
from django.urls import clear_url_caches

from examples.integration import http

ROUNDTRIP = {"a": "  padded  ", "b": "", "c": None, "d": {}, "e": [{}], "f": [], "g": 1.5, "h": "naïve — 東京",
             "i": {"j": {"k": [1, "x", True]}}}
"""The contract test's round-trip document."""

DOCS = "https://surveyjs.io/documentation/backend-integration-django"


class ApiClient:
    """Django's test client, sending demo_user (alice unless said otherwise) as a cookie on each call."""

    def __init__(self, client: Client) -> None:
        self.client = client

    def request(self, method: str, path: str, *, user: str | None = "alice", json_body: Any = None, body: bytes | str | None = None,
                content_type: str = "application/json", data: Any = None, headers: dict[str, str] | None = None) -> Any:
        self.client.cookies.clear()
        if user is not None:
            self.client.cookies["demo_user"] = user
        if data is not None:   # a multipart form, as a browser posts files
            return self.client.post(path, data, headers=headers)
        payload = json.dumps(json_body) if json_body is not None else (body or b"")
        return self.client.generic(method, path, payload, content_type=content_type, headers=headers)

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> Any:
        return self.request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> Any:
        return self.request("DELETE", path, **kwargs)


def body(response: Any) -> tuple[int, Any]:
    return response.status_code, json.loads(response.content)


def page_config(html: str) -> dict[str, Any]:
    """window.SURVEYJS_PAGE from a rendered page (its json_script element)."""
    found = re.search(r'<script id="surveyjs-page" type="application/json">(.*?)</script>', html, re.S)
    assert found, "the page writes the surveyjs-page JSON"
    assert 'window.SURVEYJS_PAGE = JSON.parse(document.getElementById("surveyjs-page").textContent);' in html
    return json.loads(found.group(1))


@contextmanager
def switched(**switches: Any) -> Iterator[None]:
    """Run with these settings (VALIDATE_RESPONSES=True, …) and the URLconf imported again with them, as a restart
    would; afterwards, the settings and the URLconf as they were."""
    import config.urls
    import examples.urls

    def reload() -> None:
        importlib.reload(examples.urls)
        importlib.reload(config.urls)
        clear_url_caches()
    try:
        with override_settings(**switches):
            reload()
            yield
    finally:
        reload()


Handler = Callable[[httpx2.Request], httpx2.Response]


class MockService:
    """The SurveyJS service (or any outbound call), answered by a handler; counts the calls. Use as a context."""

    def __init__(self, handler: Handler) -> None:
        self.calls: list[httpx2.Request] = []
        self.handler = handler

    def _record(self, request: httpx2.Request) -> httpx2.Response:
        self.calls.append(request)
        return self.handler(request)

    def __enter__(self) -> "MockService":
        http.use_transport(httpx2.MockTransport(self._record))
        return self

    def __exit__(self, *exc: Any) -> None:
        http.use_transport(None)


def answer(status: int, payload: Any = None, *, content: bytes | None = None, content_type: str = "application/json") -> Handler:
    data = content if content is not None else json.dumps(payload).encode()
    return lambda request: httpx2.Response(status, content=data, headers={"Content-Type": content_type})


def asgi_client(**kwargs: Any) -> httpx2.AsyncClient:
    """A client for config.asgi.application itself: the body limit, the sandbox and Django, as uvicorn runs them."""
    from config.asgi import application
    return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=application), base_url="http://testserver", **kwargs)


class Socket:
    """A WebSocket connection to config.asgi.application, through asgiref's ApplicationCommunicator (Channels'
    WebsocketCommunicator would import Daphne)."""

    def __init__(self, path: str, user: str | None = "alice", sid: str | None = None) -> None:
        from config.asgi import application
        route, _, query = path.partition("?")
        cookies = "; ".join([f"demo_user={user}"] * (user is not None) + [f"demo_sid={sid}"] * (sid is not None))
        scope = {"type": "websocket", "asgi": {"version": "3.0"}, "scheme": "ws", "path": route,
                 "raw_path": route.encode(), "query_string": query.encode(), "root_path": "",
                 "headers": [(b"host", b"testserver")] + ([(b"cookie", cookies.encode())] if cookies else []),
                 "subprotocols": [], "client": ("127.0.0.1", 50000), "server": ("testserver", 80)}
        self.communicator = ApplicationCommunicator(application, scope)

    async def connect(self) -> bool:
        """True when the relay accepted the handshake, False when it closed it first."""
        await self.communicator.send_input({"type": "websocket.connect"})
        message = await self.communicator.receive_output(5)
        return message["type"] == "websocket.accept"

    async def send(self, message: Any) -> None:
        await self.communicator.send_input({"type": "websocket.receive", "text": json.dumps(message)})

    async def send_text(self, text: str) -> None:
        await self.communicator.send_input({"type": "websocket.receive", "text": text})

    async def receive(self, timeout: float = 5) -> dict[str, Any]:
        message = await self.communicator.receive_output(timeout)
        assert message["type"] == "websocket.send", message
        return json.loads(message["text"])

    async def next_of(self, kind: str) -> dict[str, Any]:
        """The next message of a type, skipping the others (a peer's presence, say)."""
        for _ in range(50):
            message = await self.receive()
            if message["type"] == kind:
                return message
        raise AssertionError(f"no {kind} message")

    async def close(self) -> None:
        await self.communicator.send_input({"type": "websocket.disconnect", "code": 1000})
        await self.communicator.wait(5)


def drop_sandbox_aliases() -> None:
    """Close and forget the database aliases demo/sandbox.py registered (Django's test teardown expects only the
    aliases it saw when the class started)."""
    for alias in [alias for alias in connections.settings if alias.startswith("sandbox_")]:
        connections[alias].close()
        try:
            del connections[alias]
        except AttributeError:
            pass
        del connections.settings[alias]


class _WithSandboxes(frozenset):
    """The default database, and every sandbox alias demo/sandbox.py registers while a test runs."""

    def __contains__(self, alias: object) -> bool:
        return (isinstance(alias, str) and alias.startswith("sandbox_")) or super().__contains__(alias)


class SandboxTestCase(TransactionTestCase):
    """Tests that drive config.asgi.application in demo mode, where requests reach visitor sandboxes: Django's test
    isolation refuses queries to databases a test doesn't declare, and these appear while it runs."""

    databases = _WithSandboxes({"default"})

    @classmethod
    def _validate_databases(cls) -> frozenset[str]:   # Django makes `databases` a plain frozenset here
        return _WithSandboxes(super()._validate_databases())

    def tearDown(self) -> None:
        drop_sandbox_aliases()
        super().tearDown()
