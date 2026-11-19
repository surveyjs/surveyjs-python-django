"""Demo only: with DEMO_MODE=true each visitor works in a private copy of the seeded database and an uploads
folder, chosen by the demo_sid cookie. The example views don't change: this middleware registers the copy as a
database alias and sets the context variable examples/db.py's router returns, so the ORM writes there, and it
puts the uploads folder and the sandbox id into the ASGI scope.

Pure ASGI, wrapped around the whole app in config/asgi.py, so it runs for the WebSocket relays too: they seed
rooms from and save into the same copy. Outside demo mode it does nothing. Delete this file (and its line in
config/asgi.py) when you copy an example into your app.
"""

import asyncio
import logging
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs

from django.conf import settings
from django.db import connections
from django.http.cookie import parse_cookie

from examples.db import sandbox_database

log = logging.getLogger("demo")

TTL_HOURS = 24
_ID = re.compile(r"^[0-9a-f]{32}$")
_MONTH = 30 * 24 * 3600
_creating = threading.Lock()


@dataclass(frozen=True)
class Sandbox:
    id: str
    database: Path
    uploads: Path

    @property
    def alias(self) -> str:
        return f"sandbox_{self.id}"


def is_valid_id(value: object) -> bool:
    """128 random bits as 32 lowercase hex characters; nothing else ever reaches a file path."""
    return isinstance(value, str) and _ID.match(value) is not None


def new_id() -> str:
    return secrets.token_hex(16)


def sandbox_dir() -> Path:
    return Path(settings.DATA_DIR) / "sandbox"


def _paths(sandbox_id: str) -> Sandbox:
    return Sandbox(sandbox_id, sandbox_dir() / f"{sandbox_id}.sqlite", sandbox_dir() / sandbox_id)


def exists(sandbox_id: object) -> bool:
    return is_valid_id(sandbox_id) and _paths(str(sandbox_id)).database.is_file()


def resolve(sandbox_id: str) -> Sandbox:
    """The visitor's sandbox, created from the seeded database on first use, registered as a database alias, and
    marked as used now."""
    if not is_valid_id(sandbox_id):
        raise ValueError("Invalid sandbox id")
    sandbox = _paths(sandbox_id)
    with _creating:
        if not sandbox.database.is_file():
            sandbox.uploads.mkdir(parents=True, exist_ok=True)
            # backup(), not a file copy: the seeded database is in WAL mode and may have pages in its -wal file
            source = sqlite3.connect(connections.settings["default"]["NAME"])
            target = sqlite3.connect(sandbox.database)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        if sandbox.alias not in connections.settings:
            connections.settings[sandbox.alias] = {**connections.settings["default"], "NAME": sandbox.database}
    os.utime(sandbox.database)   # last used: prune() removes sandboxes unused for 24 hours
    return sandbox


def prune(now: float | None = None) -> int:
    """Remove sandboxes (and relay snapshots) unused for 24 hours. config/lifespan.py runs it hourly in demo mode;
    `python manage.py prune_sandboxes` runs it from cron."""
    cutoff = (now or time.time()) - TTL_HOURS * 3600
    removed = 0
    folder = sandbox_dir()
    for database in sorted(folder.glob("*.sqlite")) if folder.is_dir() else []:
        if not is_valid_id(database.stem) or database.stat().st_mtime >= cutoff:
            continue
        with _creating:
            connections.settings.pop(f"sandbox_{database.stem}", None)   # before the file: no new connections to it
            try:
                for suffix in ("", "-wal", "-shm"):
                    Path(f"{database}{suffix}").unlink(missing_ok=True)
            except OSError as error:   # Windows: a connection still holds it; the next run tries again
                log.warning("Couldn't remove sandbox %s yet: %s", database.stem, error)
                continue
        shutil.rmtree(folder / database.stem, ignore_errors=True)
        removed += 1
    relay = Path(settings.DATA_DIR) / "relay"
    for snapshot in relay.glob("*.json") if relay.is_dir() else []:
        if snapshot.stat().st_mtime < cutoff:
            snapshot.unlink(missing_ok=True)
    return removed


class DemoSandbox:
    """Resolves the visitor's sandbox from demo_sid, or from an invite link's ?join=<id>, on every request."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if (not settings.DEMO_MODE or scope["type"] not in ("http", "websocket")
                or scope["path"] == "/up" or scope["path"].startswith(("/shared/", "/static/"))):   # no database
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers", []))
        sandbox_id = parse_cookie(headers.get(b"cookie", b"").decode("latin-1")).get("demo_sid")
        issue_cookie = join_failed = False

        # An invite link (?join=<id>) adopts the inviter's sandbox, after the same format check
        join = parse_qs(scope.get("query_string", b"").decode("latin-1")).get("join", [None])[-1]
        if join is not None and scope["type"] == "http" and not scope["path"].startswith("/api/"):
            if exists(join):
                issue_cookie, sandbox_id = sandbox_id != join, join
            else:
                join_failed, sandbox_id = True, None   # the page header says the invite has expired

        scope = {**scope, "demo_join_failed": join_failed}
        if not is_valid_id(sandbox_id):
            if scope["type"] == "websocket":   # a relay can't set a cookie: no sandbox, so the relay refuses
                return await self.app(scope, receive, send)
            sandbox_id, issue_cookie = new_id(), True   # never a file path built from client input
        sandbox = await asyncio.to_thread(resolve, str(sandbox_id))
        scope.update(demo_sid=sandbox.id, uploads=sandbox.uploads)

        if issue_cookie:
            send = self._with_cookie(send, sandbox.id, secure=scope.get("scheme") in ("https", "wss"))
        token = sandbox_database.set(sandbox.alias)   # the ORM's router reads it (examples/db.py)
        try:
            await self.app(scope, receive, send)
        finally:
            sandbox_database.reset(token)

    @staticmethod
    def _with_cookie(send, sandbox_id: str, secure: bool):
        cookie = SimpleCookie()
        cookie["demo_sid"] = sandbox_id
        cookie["demo_sid"].update({"max-age": _MONTH, "path": "/", "samesite": "Lax", "httponly": True, "secure": secure})
        header = cookie["demo_sid"].OutputString().encode("latin-1")

        async def send_with_cookie(message) -> None:
            if message["type"] == "http.response.start":
                message = {**message, "headers": [*message.get("headers", []), (b"set-cookie", header)]}
            await send(message)
        return send_with_cookie
