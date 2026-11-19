"""Demo only: on the hosted demo (DEMO_MODE=true) a file over 5 MB answers 413, before any other check of the batch,
as the reference's middleware does. Off the demo, /api/files answers 422 and the scan 413, as the contract says.
Django parses the multipart body once: the view reads the same request.FILES. Delete this file (and its
MIDDLEWARE line) when you copy an example."""

from django.conf import settings
from django.http import JsonResponse

from examples.middleware import SyncAndAsyncMiddleware

MAX_BYTES = 5 * 1024 * 1024
PATHS = ("/api/files", "/api/work-orders/extract")


class DemoUploadLimitMiddleware(SyncAndAsyncMiddleware):
    def process_request(self, request):
        if (not settings.DEMO_MODE or request.method != "POST" or request.path not in PATHS
                or not request.content_type.startswith("multipart/")):
            return None
        if any(file.size > MAX_BYTES for _, files in request.FILES.lists() for file in files):
            return JsonResponse({"error": "Files over 5 MB are not accepted on the demo"}, status=413)
        return None
