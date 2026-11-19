"""Demo only: in demo mode a room belongs to one visitor sandbox, so its key is "<demo_sid>:<id>", and visitors in
different sandboxes never share a room. Outside demo mode the key is the plain record or form id. The consumers
get their key from for_scope(), outside their regions; the Data panel names snapshots with the same helper."""

import hashlib
import json
from pathlib import Path
from typing import Any

from django.conf import settings

from examples.integration.stored_json import created_at


def room_key(sandbox_id: str | None, id: str) -> str:
    """The room key for a record or form id, in a sandbox (demo mode) or not."""
    return f"{sandbox_id}:{id}" if sandbox_id else id


def for_scope(scope: dict[str, Any], id: str) -> str | None:
    """The connection's room key, or None in demo mode without a sandbox (the relay then refuses it)."""
    if not settings.DEMO_MODE:
        return id
    sandbox_id = scope.get("demo_sid")   # set by demo/sandbox.py
    return room_key(sandbox_id, id) if sandbox_id else None


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def group_name(relay: str, key: str) -> str:
    """The room's channel-layer group: group names allow letters, digits, - _ and . only, room keys contain ":"."""
    return f"{relay}.{_digest(key)}"


def snapshot_path(key: str, relay: str = "fill") -> Path:
    """Where a relay writes a room snapshot for the Data panel (demo/views.py reads it). Room keys contain ":"
    (invalid in Windows file names) and ids from the URL, so the file is named by the key's SHA-256."""
    name = f"{_digest(key)}.json"
    return Path(settings.DATA_DIR) / "relay" / (name if relay == "fill" else f"{relay}-{name}")


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**snapshot, "updatedAt": created_at()}, indent=4, ensure_ascii=False), encoding="utf-8")
