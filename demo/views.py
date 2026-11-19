"""Demo only: GET /demo/stored/<slug>, the Data panel ("What the server stored"). A fixed, whitelisted read per
example through the ORM, never arbitrary SQL. The section names and row fields are the reference's
(App\\Support\\Demo::stored()): the contract test and the browser tests read them."""

import json
import re
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db.models import Model
from django.http import Http404, HttpRequest, JsonResponse

from examples.db import JsonExtract, rowid
from examples.models import Claim, Customer, File, Form, Office, Progress, Response, ShippingRate, VariablePreset
from examples.relay.room_key import room_key, snapshot_path

_ROOM = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ID = re.compile(r"^\s*\+?\d+\s*$")


def _responses(form_id: str | None, id: int | None, limit: int = 5, customer_email: str | None = None) -> list[dict[str, Any]]:
    rows = Response.objects.order_by("-id")
    if form_id:
        rows = rows.filter(form_id=form_id)
    if id:
        rows = rows.filter(id=id)
    if customer_email is not None:
        rows = rows.annotate(email=JsonExtract("data", "$.customer_email")).filter(email=customer_email)
    return [{"data": json.loads(row.data), "id": row.id, "form_id": row.form_id,
             "definition_version": row.definition_version, "created_at": row.created_at} for row in rows[:limit]]


def _document(model: type[Model], key: str) -> dict[str, Any] | None:
    row = model.objects.filter(key=key).first()
    return {"key": key, "json": json.loads(row.json)} if row else None


def _amount(value: Any) -> float | None:
    return None if value is None else float(value)


def _claims(id: int | None, limit: int = 3) -> dict[str, list[dict[str, Any]]]:
    rows = Claim.objects.select_related("response").order_by("-id")
    rows = list(rows.filter(response_id=id)[:limit] if id else rows[:limit])
    return {
        "claims": [{"claim_id": c.id, "response_id": c.response_id, "customer_email": c.customer_email,
                    "amount": _amount(c.amount)} for c in rows],
        "responses": [{"id": c.response.id, "form_id": c.response.form_id, "definition_version": c.response.definition_version,
                       "created_at": c.response.created_at, "data": json.loads(c.response.data)} for c in rows],
    }


def _files(limit: int) -> list[dict[str, Any]]:
    """The latest uploads first: ids are UUIDs, so by SQLite's rowid (insertion order)."""
    return list(File.objects.order_by(rowid().desc()).values("id", "name", "type")[:limit])


def _row_counts() -> dict[str, int]:
    return {"forms": Form.objects.count(), "responses": Response.objects.count(), "progress": Progress.objects.count(),
            "files": File.objects.count(), "claims": Claim.objects.count(), "variable_presets": VariablePreset.objects.count()}


def _relay_room(request: HttpRequest, relay: str) -> Any:
    room = request.GET.get("room", "")
    if not _ROOM.match(room):
        return None
    if not settings.DEMO_MODE:
        return "The relay writes room snapshots in demo mode only (DEMO_MODE=true)"
    path: Path = snapshot_path(room_key(getattr(request, "scope", {}).get("demo_sid"), room), relay)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else "No room data"


def sections(slug: str, request: HttpRequest) -> dict[str, Any] | None:
    """The Data panel's sections for an example, or None for an unknown slug."""
    raw_id = request.GET.get("id", "")
    id = int(raw_id) or None if _ID.match(raw_id) else None
    key = request.GET.get
    user = request.user
    email = user.email if user.is_authenticated else ""
    match slug:
        case "save-response":
            return {"responses": _responses(None if id else "contact", id)}
        case "load-definition-variables-data":
            return {"responses": _responses("claim", id, customer_email=None if id else email)}
        case "resume-progress":
            return {"progress": _document(Progress, f"{user.pk if user.is_authenticated else ''}:{key('key', 'onboarding')}"),
                    "responses": _responses("onboarding", id)}
        case "store-files":
            return {"responses": _responses("expenses", id, 3), "files": _files(10)}
        case "choices-from-web":
            return {
                "responses": _responses("visit", id, 3),
                "offices": list(Office.objects.order_by("region", "name").values("id", "name", "region")),
                "countries cache": "cached for 24 hours" if cache.get("countries") is not None
                else "empty: the next request fetches restcountries.com",
            }
        case "async-functions":
            return {"customers": list(Customer.objects.values_list("email", flat=True)),
                    "shipping_rates": [{"postcode_prefix": r.postcode_prefix, "price": _amount(r.price)}
                                       for r in ShippingRate.objects.order_by("postcode_prefix")]}
        case "relational-storage":
            return _claims(id)
        case "fill-together":
            return {"relay room": _relay_room(request, "fill"), "responses": _responses("job-sheet", id, 3)}
        case "dashboard":
            return {"responses": Response.objects.filter(form_id="feedback").count()}
        case "creator-load-save":
            return {"forms": _document(Form, key("key", "support"))}
        case "ai-translation":
            return {"forms": _document(Form, "support-translations")}
        case "creator-uploads":
            return {"forms": _document(Form, "support-assets"), "files": _files(5)}
        case "variable-presets":
            return {"variable_presets": _document(VariablePreset, key("key", "support"))}
        case "edit-together":
            return {"relay room": _relay_room(request, "edit"), "forms": _document(Form, key("key", "support-team"))}
        case "validate-response":
            return {"responses": _responses("claim", id)}
        case "lint-definition":
            return {"forms": _document(Form, "support-lint")}
        case "server-pdf":
            return {"responses": _responses("claim", id, 10)}
        case "extract-from-paper":
            return {"row counts": _row_counts(), "responses": _responses("work-order", id, 3)}
    return None


def stored(request: HttpRequest, slug: str) -> JsonResponse:
    found = sections(slug, request)
    if found is None:
        raise Http404("Unknown example")
    return JsonResponse(found)
