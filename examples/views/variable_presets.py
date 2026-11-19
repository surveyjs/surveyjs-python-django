"""Variable Presets: GET and PUT /api/variable-presets/<form_id>, the presets Creator's Preview tab offers."""

from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.auth import can
from examples.integration.stored_json import dumps, read_json
from examples.models import VariablePreset


# region sjs:variable-presets.server
# GET /api/variable-presets/<form_id> — return the stored preset list, or [] when none are saved
def load_presets(request: HttpRequest, form_id: str) -> HttpResponse:
    presets = VariablePreset.objects.filter(key=form_id).values_list("json", flat=True).first()
    return HttpResponse(presets or "[]", content_type="application/json")   # as stored


# PUT /api/variable-presets/<form_id> — store the variable presets as-is: it's one JSON document
def save_presets(request: HttpRequest, form_id: str) -> HttpResponse:
    if not can(request.user, "edit-forms"):   # editing is an admin action: 403 otherwise
        return JsonResponse({"error": "You don't have editor rights: only editors can change forms"}, status=403)
    # The raw body, not request.POST: the presets are stored as they arrived, {} stays {}
    VariablePreset.objects.update_or_create(key=form_id, defaults={"json": dumps(read_json(request))})
    return HttpResponse(status=204)
# endregion
