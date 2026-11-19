"""Resume Progress: GET, PUT and DELETE /api/progress/<form_id>, a draft per user and form."""

from django.http import HttpRequest, HttpResponse, JsonResponse

from examples.integration.stored_json import dumps, read_json
from examples.models import Progress


# region sjs:resume-progress.server
# Return the current user's saved answers and UI state, or null when there is no draft
def load_progress(request: HttpRequest, form_id: str) -> HttpResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to load progress"}, status=401)
    draft = Progress.objects.filter(key=f"{request.user.pk}:{form_id}").values_list("json", flat=True).first()
    return HttpResponse(draft or "null", content_type="application/json")   # as stored


# Store progress under a key containing both the user ID and form ID
def save_progress(request: HttpRequest, form_id: str) -> HttpResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to save progress"}, status=401)
    # The raw body, not request.POST: { data, uiState } is stored as it arrived, {} stays {}
    Progress.objects.update_or_create(key=f"{request.user.pk}:{form_id}", defaults={"json": dumps(read_json(request))})
    return HttpResponse(status=204)
# endregion


# region sjs:resume-progress.delete
# Remove only the current user's draft
def delete_progress(request: HttpRequest, form_id: str) -> HttpResponse:
    if not request.user.is_authenticated:
        return JsonResponse({"error": "Sign in to clear progress"}, status=401)
    Progress.objects.filter(key=f"{request.user.pk}:{form_id}").delete()
    return HttpResponse(status=204)
# endregion
