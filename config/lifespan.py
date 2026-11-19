"""The ASGI lifespan, which Django itself ignores: uvicorn runs with lifespan="on", and this wrapper answers it.

At startup in demo mode it starts the hourly sandbox pruner (demo only; Django has no scheduler, and one task in
the app's one process is enough here). At shutdown it stops the pruner and closes the outbound HTTP client.
"""

import asyncio
import logging
from contextlib import suppress

from django.conf import settings

from examples.integration import http

log = logging.getLogger("demo")
PRUNE_EVERY_SECONDS = 3600


async def prune_hourly() -> None:
    """Demo only: remove visitor sandboxes unused for 24 hours, every hour."""
    from demo.sandbox import prune

    while True:
        try:
            removed = await asyncio.to_thread(prune)
            if removed:
                log.info("Removed %d visitor sandboxes unused for 24 hours", removed)
        except OSError:
            log.exception("Pruning visitor sandboxes failed")
        await asyncio.sleep(PRUNE_EVERY_SECONDS)


class Lifespan:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "lifespan":
            return await self.app(scope, receive, send)
        pruner: asyncio.Task[None] | None = None
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                if settings.DEMO_MODE:
                    pruner = asyncio.create_task(prune_hourly())
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                if pruner is not None:
                    pruner.cancel()
                    with suppress(asyncio.CancelledError):
                        await pruner
                await http.aclose()
                await send({"type": "lifespan.shutdown.complete"})
                return
