"""The app's outbound HTTP client, for the SurveyJS service, the AI provider and restcountries.com: one
httpx2.AsyncClient per running event loop, created on first use, so connections are reused. Async: a view
that waits on one of them doesn't stop the app from serving anyone else (README: Sync and async views).

Django has no lifespan of its own: config/lifespan.py closes the client when uvicorn shuts down. Tests replace
the transport with use_transport(httpx2.MockTransport(...)).
"""

import asyncio
from weakref import WeakKeyDictionary

import httpx2

_clients: WeakKeyDictionary[asyncio.AbstractEventLoop, httpx2.AsyncClient] = WeakKeyDictionary()
_transport: httpx2.AsyncBaseTransport | None = None


def client() -> httpx2.AsyncClient:
    """The client of the running event loop (uvicorn has one; each async test has its own)."""
    loop = asyncio.get_running_loop()
    http = _clients.get(loop)
    if http is None or http.is_closed:
        http = _clients[loop] = httpx2.AsyncClient(transport=_transport, follow_redirects=False)
    return http


async def aclose() -> None:
    """Close the running loop's client (config/lifespan.py, at shutdown)."""
    http = _clients.pop(asyncio.get_running_loop(), None)
    if http is not None:
        await http.aclose()


def use_transport(transport: httpx2.AsyncBaseTransport | None) -> None:
    """Tests only: send every outbound request through this transport (None: the network again)."""
    global _transport
    _transport = transport
    _clients.clear()
