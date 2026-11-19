"""Generate PDFs: GET /api/claims/<id>/pdf, a claim filled into its definition by the SurveyJS service."""

import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.integration.surveyjs_service import SurveyJsService
from examples.models import Form, Response

DEFINITIONS = settings.BASE_DIR / "shared" / "definitions"


# region sjs:server-pdf.server
# GET /api/claims/<id>/pdf — ask the SurveyJS service for the filled form and pass the PDF through
async def claim_pdf(request: HttpRequest, claim_id: int) -> HttpResponse:
    if (claim := await Response.objects.filter(form_id="claim", id=claim_id).afirst()) is None:
        return JsonResponse({"error": "Unknown claim"}, status=404)
    match claim.definition_version:   # use the schema version recorded with the response
        case "v1" | "v2" as version:
            definition = (DEFINITIONS / f"relational-storage.{version}.json").read_text(encoding="utf-8")
        case None:
            definition = (await Form.objects.aget(key="claim")).json
        case _:
            return JsonResponse({"error": "The schema version for this claim is unavailable"}, status=409)

    surveyjs = SurveyJsService()
    pdf = await surveyjs.post("/pdf", {"schema": json.loads(definition), "response": json.loads(claim.data)}, timeout=60)
    if (pdf.status_code != 200 or not pdf.headers.get("content-type", "").startswith("application/pdf")
            or not pdf.content.startswith(b"%PDF-")):
        surveyjs.unexpected("/pdf", pdf)

    return HttpResponse(pdf.content, content_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="claim-{claim_id}.pdf"', "Cache-Control": "private, no-store"})
# endregion
