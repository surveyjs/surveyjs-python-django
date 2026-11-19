"""The API's middleware: every error under /api/ is JSON { error }, and the API takes requests without a CSRF token.

Django's own answers under /api/ would be HTML pages: the resolver's 404, a 405, RequestDataTooBig's 400, a
CSRF 403, a 500. ApiErrorMiddleware turns each into { error } with the status the contract gives. Outside /api/
the pages keep Django's handling (templates/404.html, templates/500.html).
"""

import logging

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.core.exceptions import BadRequest, PermissionDenied, RequestDataTooBig, SuspiciousOperation
from django.http import Http404, HttpRequest, HttpResponseBase, JsonResponse
from django.middleware.csrf import CsrfViewMiddleware

from examples.errors import ApiError

log = logging.getLogger("examples")

MESSAGES = {
    400: "Bad request", 401: "Unauthorized", 403: "Forbidden", 404: "Not found", 405: "Method not allowed",
    413: "The request body is too large", 415: "Unsupported media type", 422: "Unprocessable content",
    429: "Too many requests", 500: "Internal server error", 502: "Bad gateway", 503: "Service unavailable",
}


class SyncAndAsyncMiddleware:
    """A middleware Django runs in the mode of what it wraps: an async view stays on the event loop. (Django's
    MiddlewareMixin runs process_request and process_response through sync_to_async, on the one thread every
    sync view shares under ASGI.) The hooks do no I/O."""

    sync_capable = True
    async_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(self, request: HttpRequest):
        if self.async_mode:
            return self._acall(request)
        response = self.process_request(request) or self.get_response(request)
        return self.process_response(request, response)

    async def _acall(self, request: HttpRequest) -> HttpResponseBase:
        response = self.process_request(request) or await self.get_response(request)
        return self.process_response(request, response)

    def process_request(self, request: HttpRequest) -> HttpResponseBase | None:
        return None

    def process_response(self, request: HttpRequest, response: HttpResponseBase) -> HttpResponseBase:
        return response


def is_api(request: HttpRequest) -> bool:
    return request.path.startswith("/api/")


def error(status: int, message: str | None = None) -> JsonResponse:
    return JsonResponse({"error": message or MESSAGES.get(status, "Error")}, status=status)


class ApiErrorMiddleware(SyncAndAsyncMiddleware):
    """{ error } for every error under /api/, with the view's own text where it has one."""

    def process_exception(self, request: HttpRequest, exception: Exception) -> HttpResponseBase | None:
        if not is_api(request):
            return None
        match exception:
            case ApiError():                    # raised by the integration helpers (read_json, the service client)
                return error(exception.status, exception.message)
            case RequestDataTooBig():           # a body over DATA_UPLOAD_MAX_MEMORY_SIZE
                return error(413)
            case BadRequest() | SuspiciousOperation():   # TooManyFilesSent, a malformed multipart body…
                return error(400)
            case PermissionDenied():
                return error(403)
            case Http404():
                return error(404)
        log.error("Unhandled error on %s %s", request.method, request.path, exc_info=exception)
        return error(500)

    def process_response(self, request: HttpRequest, response: HttpResponseBase) -> HttpResponseBase:
        """An error page from Django itself (the resolver's 404, a 405, a CSRF 403, a 500): the same answer as JSON."""
        if not is_api(request) or response.status_code < 400 or response.get("Content-Type", "").startswith("application/json"):
            return response
        answer = error(response.status_code)
        if response.has_header("Allow"):
            answer["Allow"] = response["Allow"]
        return answer


class ApiCsrfViewMiddleware(CsrfViewMiddleware):
    """Django's CSRF protection for the pages, not for /api/.

    The shared client modules (shared/client/*.js) send no CSRF token, so CsrfViewMiddleware would refuse every
    POST, PUT and DELETE they make. The API can do without it here: the demo user's cookie is SameSite=Lax, so a
    cross-site POST arrives signed out, and signed-out saves are refused. A real app keeps CsrfViewMiddleware and
    sends the csrftoken cookie's value as an X-CSRFToken header from its fetch() calls.
    """

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if is_api(request):
            return None
        return super().process_view(request, callback, callback_args, callback_kwargs)
