"""Demo only: adds X-Demo-Cache: hit / miss / fallback to GET /api/countries, so the requests log shows where the
list came from. It notes whether Django's cache held the list before the view ran, and looks at what the cache
holds when the answer leaves: "fallback" wins whenever the bundled list is served, also while it is cached.
examples/views/choices_from_web.py stays as the docs show it. Delete this file (and its MIDDLEWARE line) when you
copy an example."""

import json

from django.conf import settings
from django.core.cache import cache

from examples.middleware import SyncAndAsyncMiddleware

BUNDLED = json.loads((settings.BASE_DIR / "shared" / "seed" / "countries.json").read_text(encoding="utf-8"))


class DemoCacheHeaderMiddleware(SyncAndAsyncMiddleware):
    def process_request(self, request):
        if request.path == "/api/countries":
            request.demo_cached_before = cache.get("countries") is not None   # LocMemCache: memory, no I/O

    def process_response(self, request, response):
        if request.path == "/api/countries" and response.status_code == 200:
            state = "fallback" if cache.get("countries") == BUNDLED else "hit" if request.demo_cached_before else "miss"
            response["X-Demo-Cache"] = state
        return response
