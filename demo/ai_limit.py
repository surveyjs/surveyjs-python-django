"""Demo only: on the hosted demo (DEMO_MODE=true), POST /api/translate and /api/work-orders/extract allow 20 calls
per visitor (demo_sid) per UTC day. The counts live in Django's cache, in this process (the app runs one, see
README): with several processes, use a shared cache such as Redis. Delete this file (and its MIDDLEWARE line)
when you copy an example."""

from datetime import UTC, datetime

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse

from examples.middleware import SyncAndAsyncMiddleware

LIMIT = 20
PATHS = ("/api/translate", "/api/work-orders/extract")


class DemoAiLimitMiddleware(SyncAndAsyncMiddleware):
    def process_request(self, request):
        if not settings.DEMO_MODE or request.method != "POST" or request.path not in PATHS:
            return None
        key = f"demo-ai:{getattr(request, 'scope', {}).get('demo_sid')}:{datetime.now(UTC):%Y-%m-%d}"
        cache.add(key, 0, timeout=2 * 24 * 3600)
        if cache.incr(key) > LIMIT:
            return JsonResponse({"error": "The demo allows 20 AI calls per visitor per day"}, status=429)
        return None
