"""Save Responses: POST /api/responses stores submitted answers as one JSON document.

examples/urls.py routes POST /api/responses to validate_response.py instead when VALIDATE_RESPONSES=true.
"""

from django.http import HttpRequest, JsonResponse

from examples.integration.stored_json import insert_response, read_json


# region sjs:save-response.server
# POST /api/responses: Store submitted answers as one JSON document
def save(request: HttpRequest) -> JsonResponse:
    # The raw body, not request.POST or a serializer: json.loads keeps every key and value as it was sent
    body = read_json(request)
    if not isinstance(body, dict) or "formId" not in body or "data" not in body:
        return JsonResponse({"error": "Expected { formId, data }"}, status=400)

    id = insert_response(body["formId"], body["data"])   # stored as it arrived: {} stays {}, 1.0 stays 1.0

    return JsonResponse({"id": id}, status=201)
# endregion
