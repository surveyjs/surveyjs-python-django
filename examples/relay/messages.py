"""What both relays do with a frame and a name: parse the JSON (objects stay objects, {} is relayed as {}), and
take the participant's name from ?name=. Used by examples/consumers/fill_together.py and edit_together.py."""

import json
from typing import Any
from urllib.parse import parse_qs


def _reject_constant(name: str) -> Any:
    raise ValueError(name)


def parse(raw: str | None) -> Any:
    """A message as JSON, or None (a binary frame, or text that isn't JSON)."""
    try:
        return json.loads(raw, parse_constant=_reject_constant) if raw is not None else None
    except (ValueError, RecursionError):
        return None


def display_name(scope: dict[str, Any], fallback: str) -> str:
    """The name from ?name=, trimmed to 32 characters, or the user's name."""
    name = parse_qs(scope.get("query_string", b"").decode("utf-8", "replace")).get("name", [""])[-1]
    return name.strip()[:32] or fallback
