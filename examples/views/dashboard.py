"""Analyze Results with Dashboard: GET /api/responses, the stored documents of one form, filtered and paged."""

import json

from django.db.models.functions import Substr
from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.models import Response


# region sjs:dashboard.server
# GET /api/responses?formId=&includeCreatedAt=&from=&to=&limit=&offset=
def responses(request: HttpRequest) -> HttpResponse:
    query = request.GET
    try:   # page on the server for large volumes
        limit, offset = min(max(int(query.get("limit", 500)), 1), 5000), max(int(query.get("offset", 0)), 0)
    except ValueError:
        return JsonResponse({"error": "limit and offset must be whole numbers"}, status=400)
    rows = Response.objects.filter(form_id=query.get("formId", ""), created_at__gte=query.get("from", ""))
    if to := query.get("to"):   # ISO 8601 UTC strings compare as dates; `to` includes that whole day
        rows = rows.annotate(day=Substr("created_at", 1, 10)).filter(day__lte=to)
    rows = rows.order_by("created_at", "id").values_list("data", "created_at")[offset:offset + limit]

    # Include submission dates separately when requested by Dashboard
    if query.get("includeCreatedAt") in ("1", "true"):
        return JsonResponse([{"data": json.loads(data), "createdAt": created_at} for data, created_at in rows], safe=False)
    return HttpResponse("[" + ",".join(data for data, _ in rows) + "]", content_type="application/json")   # as stored
# endregion
