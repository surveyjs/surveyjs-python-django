"""Seeds the tables from shared/seed/*.json, the files every platform seeds from, after `migrate`.

Idempotent: an existing database keeps its data and only gains the forms it is missing. ExamplesConfig.ready()
connects it to post_migrate, so `python manage.py migrate` (and `manage.py serve`, which runs it) leaves a fresh
DATA_DIR ready for the first request.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import transaction

from examples.integration.stored_json import created_at, dumps
from examples.models import Claim, Customer, Form, Office, Response, ShippingRate, User, VariablePreset


def _shared(path: str) -> Any:
    return json.loads((settings.BASE_DIR / "shared" / path).read_text(encoding="utf-8"))


def _days_ago(days: int) -> str:
    """The reference's times: `days` back, at 09:00 + days % 9 hours and (days * 7) % 60 minutes, UTC."""
    moment = datetime.now(UTC) - timedelta(days=days)
    return created_at(moment.replace(hour=9 + days % 9, minute=(days * 7) % 60, second=0, microsecond=0))


def seed_after_migrate(sender: Any, using: str = "default", **kwargs: Any) -> None:
    seed(using)


def seed(using: str = "default") -> bool:
    """Seed the database behind `using`. Returns True when it seeded an empty one."""
    # Every form in seed/forms.json, also into an existing database that lacks one
    forms = _shared("seed/forms.json")
    existing = set(Form.objects.using(using).filter(key__in=forms).values_list("key", flat=True))
    Form.objects.using(using).bulk_create(
        Form(key=key, json=dumps(_shared(f"definitions/{file}"))) for key, file in forms.items() if key not in existing)

    if User.objects.using(using).exists():
        return False
    with transaction.atomic(using=using):
        _seed_rows(using)
    return True


def _seed_rows(using: str) -> None:
    # Demo only: Alice (premium, editor) and Bob (basic, viewer); demo/users.py signs them in from a cookie. Editors
    # may save definitions and variable presets: the examples.edit_forms permission (examples/auth.py).
    editors = Group.objects.using(using).create(name="Editors")
    editors.permissions.add(Permission.objects.using(using).get(codename="edit_forms", content_type__app_label="examples"))
    for username, first, last, plan in (("alice", "Alice", "Martin", "premium"), ("bob", "Bob", "Fischer", "basic")):
        user = User(username=username, first_name=first, last_name=last, email=f"{username}@example.com", plan=plan)
        user.set_unusable_password()
        user.save(using=using)
        if username == "alice":
            user.groups.add(editors)

    Office.objects.using(using).bulk_create(Office(id=o["id"], name=o["name"], region=o["region"]) for o in _shared("seed/offices.json"))
    Customer.objects.using(using).bulk_create(Customer(email=email) for email in _shared("seed/customers.json"))
    ShippingRate.objects.using(using).bulk_create(
        ShippingRate(postcode_prefix=r["postcode_prefix"], price=str(r["price"])) for r in _shared("seed/shipping-rates.json"))

    def response(form_id: str, data: Any, when: str, version: str | None = None) -> Response:
        return Response(form_id=form_id, definition_version=version, data=dumps(data), created_at=when)

    for claim in _shared("seed/claims.json"):
        saved = response("claim", claim["data"], _days_ago(claim["daysAgo"]), claim["definitionVersion"])
        saved.save(using=using)
        Claim(response=saved, customer_email=claim["data"]["customer_email"], amount=str(claim["data"]["amount"])).save(using=using)
    Response.objects.using(using).bulk_create(
        [response("job-sheet", sheet["data"], _days_ago(sheet["daysAgo"])) for sheet in _shared("seed/job-sheets.json")]
        + [response("feedback", row["data"], _days_ago(row["daysAgo"])) for row in _shared("seed/feedback-responses.json")])

    VariablePreset.objects.using(using).bulk_create(
        VariablePreset(key=form_id, json=dumps(presets)) for form_id, presets in _shared("seed/variable-presets.json").items())

    # load-definition-variables-data: one claim request per demo user, saved now
    Response.objects.using(using).bulk_create(response("claim", data, created_at()) for data in _shared("seed/claim-requests.json"))
