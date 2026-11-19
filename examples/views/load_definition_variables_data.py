"""Load JSON Schemas, Variables, and Answers: GET /claim (Option A) and GET /api/forms/<id> (Option B).

Creator, the Dashboard and the other Creator examples read .definition from the same GET /api/forms/<id>.
"""

import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.db import JsonExtract
from examples.models import Form, Response
from examples.pages import render_example

DEFINITION = settings.BASE_DIR / "shared" / "definitions" / "load-definition-variables-data.json"


# region sjs:load-definition-variables-data.server
# Option A: Embed the schema and user variables in the HTML response
def claim_page(request: HttpRequest) -> HttpResponse:
    definition = json.loads(DEFINITION.read_text(encoding="utf-8"))
    user = request.user
    variables = {"user": {"name": user.get_full_name(), "plan": user.plan} if user.is_authenticated else {"name": None, "plan": None}}
    # The template writes both with json_script, which escapes them for the page
    return render_example(request, "load-definition-variables-data", form_definition=definition, form_variables=variables)


# Option B: Return the definition, variables, and previous answers in one response
def get_form(request: HttpRequest, form_id: str) -> JsonResponse:
    if (form := Form.objects.filter(key=form_id).first()) is None:
        return JsonResponse({"error": "Unknown form"}, status=404)
    user, record = request.user, request.GET.get("record", "")
    saved = Response.objects.filter(id=record) if record.isdigit() else Response.objects.none()
    if form_id == "claim-request":   # only the signed-in customer's own claims
        email = user.email if user.is_authenticated else ""
        saved = saved.annotate(email=JsonExtract("data", "$.customer_email")).filter(form_id="claim", email=email)
    answers = saved.values_list("data", flat=True).first()
    return JsonResponse({
        "definition": json.loads(form.json),                    # the stored form definition
        "variables": {"user": {"name": user.get_full_name(), "plan": user.plan} if user.is_authenticated else {"name": None, "plan": None}},
        "data": json.loads(answers) if answers else {},         # previous answers, or {} without them
    })
# endregion
