"""Use Relational Storage: POST /api/claims keeps the original JSON and its version, then copies the stable answer
keys (valueName) into the claims columns, in one transaction."""

from django.db import router, transaction
from django.http import HttpRequest, JsonResponse

from examples.integration.stored_json import insert_response, read_json
from examples.models import Claim


# region sjs:relational-storage.server
# POST /api/claims — original JSON first, then the columns you query
def save_claim(request: HttpRequest) -> JsonResponse:
    # The raw body, not request.POST: the stored answers keep every key, {} and 1.0 as they arrived
    body = read_json(request)
    if not isinstance(body, dict) or body.get("data") is None or body.get("definitionVersion") is None:
        return JsonResponse({"error": "Expected { data, definitionVersion }"}, status=400)
    data = body["data"]
    answers = data if isinstance(data, dict) else {}

    with transaction.atomic(using=router.db_for_write(Claim)):   # both rows or neither, in the router's database
        id = insert_response("claim", data, body["definitionVersion"])   # the original and its version
        Claim.objects.create(response_id=id, customer_email=answers.get("customer_email"),   # keys come from valueName
                             amount=answers.get("amount"))

    return JsonResponse({"id": id}, status=201)
# endregion
