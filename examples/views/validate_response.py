"""Validate Responses: POST /api/responses validated by the SurveyJS service before it is stored.

examples/urls.py routes POST /api/responses here instead of save_response.py when VALIDATE_RESPONSES=true. The
service is SurveyJS Server, next to this app: see docker-compose.yml and SURVEYJS_SERVICE_URL in settings.env.
Async: the view waits on the network without holding Django's one thread for sync code.
"""

import json
from contextlib import suppress
from typing import Any

from django.http import HttpRequest, JsonResponse

from examples.integration.stored_json import ainsert_response, read_json
from examples.integration.surveyjs_service import SurveyJsService
from examples.models import Form


# region sjs:validate-response.server
# POST /api/responses — ask the SurveyJS service to validate, then store as usual
async def save(request: HttpRequest) -> JsonResponse:
    # The raw body, not request.POST: the stored answers keep every key, {} and 1.0 (see Save Responses)
    body = read_json(request)
    if not isinstance(body, dict) or not isinstance(body.get("formId"), str) or not isinstance(body.get("data"), dict):
        return JsonResponse({"error": "Expected { formId, data } with an answers object"}, status=400)
    if (form := await Form.objects.filter(key=body["formId"]).afirst()) is None:
        return JsonResponse({"error": "Unknown form"}, status=404)

    surveyjs = SurveyJsService()
    check = await surveyjs.post("/response", {"schema": json.loads(form.json), "response": body["data"]}, timeout=10)
    answer: Any = None
    with suppress(ValueError):   # not JSON: fails closed below
        answer = json.loads(check.content)
    if check.status_code == 422 and isinstance(answer, dict) and "errors" in answer:
        if "warnings" in answer:   # the stored definition itself has errors
            surveyjs.unexpected("/response", check, "The stored definition has errors")
        return JsonResponse({"errors": answer["errors"]}, status=400)   # the answers don't fit the definition
    if check.status_code != 200 or answer != {}:   # fail closed: only exactly {} means valid
        surveyjs.unexpected("/response", check)

    return JsonResponse({"id": await ainsert_response(body["formId"], body["data"])}, status=201)   # 1.0 stays 1.0
# endregion
