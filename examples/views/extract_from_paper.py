"""Extract Responses from Documents: a blank, fillable work order, and the answers the SurveyJS service reads from a
completed one. Nothing is saved here: the visitor reviews the draft and the page posts it to /api/responses."""

import base64
import json
from contextlib import suppress
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.integration.file_type import detect_type
from examples.integration.surveyjs_service import SurveyJsService
from examples.models import Form

MAX_BYTES = 5 * 1024 * 1024


# region sjs:extract-from-paper.template
# Generate a blank, fillable PDF using the same schema as extraction
async def blank_work_order(request: HttpRequest) -> HttpResponse:
    if (form := await Form.objects.filter(key="work-order").afirst()) is None:
        return JsonResponse({"error": "Unknown work order form"}, status=404)
    surveyjs = SurveyJsService()
    pdf = await surveyjs.post("/pdf", {"schema": json.loads(form.json)}, timeout=60)
    if (pdf.status_code != 200 or not pdf.headers.get("content-type", "").startswith("application/pdf")
            or not pdf.content.startswith(b"%PDF-")):
        surveyjs.unexpected("/pdf", pdf)

    return HttpResponse(pdf.content, content_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="work-order.pdf"', "Cache-Control": "private, no-store"})
# endregion


# region sjs:extract-from-paper.server
# POST /api/work-orders/extract — send the uploaded scan to the SurveyJS service; return a draft response
async def extract_work_order(request: HttpRequest) -> JsonResponse:
    if (scan := request.FILES.get("scan")) is None and "scan" not in request.POST:
        return JsonResponse({"error": 'Upload the scan in a field named "scan"'}, status=400)
    if scan is None or scan.size > MAX_BYTES:   # a text field named "scan" isn't a file
        return JsonResponse({"error": "The scan must be a file of 5 MB or less"}, status=413)
    if detect_type(raw := scan.read()) is None:   # by the first bytes, never the client's Content-Type
        return JsonResponse({"error": "The file is not a PDF, PNG, JPEG, WebP or GIF document"}, status=400)
    schema = json.loads((await Form.objects.aget(key="work-order")).json)
    surveyjs = SurveyJsService()
    out = await surveyjs.post("/extract", {"schema": schema, "document": base64.b64encode(raw).decode()}, timeout=120)
    result: Any = None
    with suppress(ValueError):   # JSON with base64 went out, not multipart; an answer that isn't JSON fails closed
        result = json.loads(out.content)
    match out.status_code, result:   # nothing is saved: a person reviews the draft
        case 200, {"data": dict() as answers}:
            return JsonResponse({"answers": answers, "confidence": result.get("confidence", []), "uniqueId": result.get("uniqueId")})
        case 400, {"error": "INVALID_DOCUMENT"}:
            return JsonResponse({"error": "The file is not a PDF, PNG, JPEG, WebP or GIF document"}, status=400)
        case 503, {"error": "AI_NOT_CONFIGURED"}:
            return JsonResponse({"error": "The SurveyJS service has no AI provider configured"}, status=503)
        case 502, {"error": "EXTRACTION_FAILED"}:
            return JsonResponse({"error": "Could not extract the response from the document"}, status=502)
    surveyjs.unexpected("/extract", out, log_body=False)   # fail closed, logged by status only
# endregion
