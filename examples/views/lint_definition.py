"""Lint JSON Schemas: PUT /api/forms/<id> linted by the SurveyJS service before it is stored.

examples/urls.py routes PUT /api/forms/<id> here instead of creator_load_save.py when LINT_DEFINITIONS=true.
"""

import json
from contextlib import suppress
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.auth import acan
from examples.integration.stored_json import dumps, read_json
from examples.integration.surveyjs_service import SurveyJsService
from examples.models import Form


# region sjs:lint-definition.server
# PUT /api/forms/<id> — lint the definition from Creator before storing it
async def put_form(request: HttpRequest, form_id: str) -> HttpResponse:
    if not await acan(await request.auser(), "edit-forms"):
        return JsonResponse({"error": "You don't have editor rights: only editors can change forms"}, status=403)
    definition = read_json(request)   # the raw body keeps {} as {} (see Load and Save Form JSON Schemas)
    surveyjs = SurveyJsService()
    lint = await surveyjs.post("/schema", definition, timeout=10)
    answer: Any = None
    with suppress(ValueError):   # not JSON: fails closed below
        answer = json.loads(lint.content)
    if lint.status_code == 422 and isinstance(answer, dict) and {"errors", "warnings"} <= answer.keys():
        return JsonResponse(answer, status=422)   # errors: refuse the save, report them as they are
    warnings_only = lint.status_code == 200 and isinstance(answer, dict) and list(answer) == ["warnings"]
    if not warnings_only and (lint.status_code != 200 or answer != {}):   # fail closed: nothing else is clean
        surveyjs.unexpected("/schema", lint)

    await Form.objects.aupdate_or_create(key=form_id, defaults={"json": dumps(definition)})   # 1.0 stays 1.0
    return JsonResponse({"warnings": answer["warnings"]}) if warnings_only else HttpResponse(status=204)   # warnings don't block it
# endregion
