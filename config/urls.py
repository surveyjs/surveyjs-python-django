"""
URL configuration for config project.

The integration's paths are in examples/urls.py, the demo's Data panel in demo/urls.py, and the pages around the
examples (the catalog, /examples/<slug>, the PDF loading page) in examples/pages.py. The relays' WebSocket routes
are in examples/routing.py, which config/asgi.py serves.

For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""
from django.http import HttpRequest, JsonResponse
from django.urls import include, path

from examples import pages


def up(request: HttpRequest) -> JsonResponse:
    """Health: answers without touching the database."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path('', include('examples.urls')),
    path('', include('demo.urls')),
    path('', pages.catalog),
    path('examples/server-pdf/loading', pages.pdf_loading),
    path('examples/<str:slug>', pages.example),
    path('up', up),
]

# Outside /api/, Django's 404 and 500 render templates/404.html and templates/500.html (with DEBUG off);
# examples/middleware.py answers JSON { error } under /api/
handler404 = 'examples.pages.not_found'
handler500 = 'examples.pages.server_error'
