"""Load and Save Form JSON Schemas: PUT /api/forms/<id> stores a definition from Survey Creator.

GET /api/forms/<id> is in load_definition_variables_data.py: Creator reads its .definition. This file holds only
the PUT, so examples/urls.py can route to lint_definition.py in its place when LINT_DEFINITIONS=true.
"""

from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.auth import can
from examples.integration.stored_json import dumps, read_json
from examples.models import Form


# region sjs:creator-load-save.server
# PUT /api/forms/<id> — store the definition as-is: it's one JSON document
def put_form(request: HttpRequest, form_id: str) -> HttpResponse:
    if not can(request.user, "edit-forms"):   # editing is an admin action: 403 otherwise
        return JsonResponse({"error": "You don't have editor rights: only editors can change forms"}, status=403)
    # The raw body, not request.POST or a serializer: a serializer would drop the keys it doesn't declare
    Form.objects.update_or_create(key=form_id, defaults={"json": dumps(read_json(request))})   # {} stays {}, 1.0 stays 1.0
    return HttpResponse(status=204)   # the next page load renders the new version
# endregion
