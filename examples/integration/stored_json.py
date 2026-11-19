"""Stores SurveyJS JSON (responses, definitions, saved progress, variable presets) exactly as it arrived.

A response or a definition is one JSON document: store it as text, never as columns. Used by save-response,
resume-progress, relational-storage, creator-load-save, variable-presets, validate-response, lint-definition
and the fill-together relay. When you copy one of them, copy this file too.

Why the raw body (request.body) and not a parsed form or a serializer: json.loads keeps every key, {}, [{}],
None, "" and 1.0 as they were sent. A TextField keeps the text as written; a JSONField would decode it on every
read and encode it again on every save.
"""

import json
from datetime import UTC, datetime
from typing import Any

from django.http import HttpRequest

from examples.errors import ApiError
from examples.models import Response


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not JSON")


def read_json(request: HttpRequest) -> Any:
    """The request body as parsed JSON, or 400. Python accepts NaN and Infinity; JSON doesn't, so neither do we.

    Read it before anything touches request.POST: after that, Django refuses request.body."""
    try:
        return json.loads(request.body, parse_constant=_reject_constant)
    except (ValueError, RecursionError):   # JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise ApiError(400, "The request body is not valid JSON") from None


def dumps(value: Any) -> str:
    """JSON text for storage: ensure_ascii=False keeps "naïve — 東京" readable, compact separators, 1.0 stays 1.0."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def created_at(moment: datetime | None = None) -> str:
    """ISO 8601 UTC without fractions, 2026-11-19T09:00:00Z: dates filter as string comparisons. A DateTimeField
    would store "2026-11-19 09:00:00.000000" in SQLite, and isoformat() writes +00:00 and microseconds."""
    return (moment or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def insert_response(form_id: Any, data: Any, definition_version: Any = None) -> int:
    """Insert one response, its answers as one JSON document, and return its id. Each view validates its own input."""
    return Response.objects.create(form_id=form_id, definition_version=definition_version, data=dumps(data),
                                   created_at=created_at()).id


async def ainsert_response(form_id: Any, data: Any, definition_version: Any = None) -> int:
    """insert_response() for async views."""
    response = await Response.objects.acreate(form_id=form_id, definition_version=definition_version,
                                              data=dumps(data), created_at=created_at())
    return response.id
