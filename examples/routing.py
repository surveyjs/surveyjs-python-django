"""Routing helpers: one view per HTTP method on a path, and the WebSocket routes of the two relays.

Django dispatches by path, and two contract paths carry methods from different examples: POST /api/responses
(save-response) and GET /api/responses (dashboard), GET /api/forms/<id> (load-definition-variables-data) and PUT
(creator-load-save). by_method() picks the view by method, so each example keeps its own module.
"""

from collections.abc import Callable
from typing import Any

from asgiref.sync import iscoroutinefunction, sync_to_async
from django.http import HttpRequest, HttpResponseBase, JsonResponse
from django.urls import path

from examples.consumers.edit_together import EditTogetherConsumer
from examples.consumers.fill_together import FillTogetherConsumer

View = Callable[..., Any]


def by_method(**views: View) -> View:
    """by_method(GET=load_form, PUT=put_form): the view for the request's method, or 405 { error } with an Allow
    header naming every method of the path. If one view is async, the dispatcher is async and runs the others
    through sync_to_async, as Django's View refuses to mix them."""
    allowed = ", ".join(sorted(views))

    def not_allowed() -> JsonResponse:
        response = JsonResponse({"error": "Method not allowed"}, status=405)
        response["Allow"] = allowed
        return response

    if not any(iscoroutinefunction(view) for view in views.values()):
        def dispatch(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
            view = views.get(request.method or "")
            return view(request, *args, **kwargs) if view else not_allowed()
        return dispatch

    async def adispatch(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponseBase:
        view = views.get(request.method or "")
        if view is None:
            return not_allowed()
        if iscoroutinefunction(view):
            return await view(request, *args, **kwargs)
        return await sync_to_async(view)(request, *args, **kwargs)
    return adispatch


# The relays, on the app's own port (config/asgi.py routes the websocket protocol here)
websocket_urlpatterns = [
    path("ws/rooms/<str:record_id>", FillTogetherConsumer.as_asgi()),   # fill-together
    path("ws/forms/<str:form_id>", EditTogetherConsumer.as_asgi()),     # edit-together
]
