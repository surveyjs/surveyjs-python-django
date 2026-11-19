"""Store Files Separately: POST /api/files stores uploads, GET /api/files/<id> serves them after an access check.

Creator's uploads (creator-uploads) post to the same endpoint.
"""

import uuid

from django.http import FileResponse, HttpRequest, JsonResponse

from examples.auth import can_read_file
from examples.db import uploads
from examples.integration.file_type import detect_type
from examples.models import File

TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif", "application/pdf"}
MAX_BYTES = 5 * 1024 * 1024


# region sjs:store-files.server
# POST /api/files — store uploads, return their ids in the same order
def upload(request: HttpRequest) -> JsonResponse:
    # Field "files[]", the name on every platform. Not request.FILES["files[]"]: that is only the last file
    files = request.FILES.getlist("files[]")
    if not files:
        return JsonResponse({"error": 'Upload one or more files in a field named "files[]"'}, status=422)
    types = [detect_type(file.read(4096)) for file in files]   # by the bytes, never the client's type
    for file, type in zip(files, types):                          # check the whole batch before storing any
        if file.size > MAX_BYTES:
            return JsonResponse({"error": "Each file must be 5 MB or less"}, status=422)
        if type not in TYPES:
            return JsonResponse({"error": f"{file.name} is not a PNG, JPEG, WebP, GIF or PDF file"}, status=422)

    storage, ids = uploads(request), []
    for file, type in zip(files, types):
        id = str(uuid.uuid4())
        storage.save(id, file)                                    # named by id, never by the client
        File.objects.create(id=id, name=file.name, type=type)
        ids.append(id)
    return JsonResponse(ids, safe=False)
# endregion


# region sjs:store-files.download
# GET /api/files/<id> — the content, for private files only; check access first
def download(request: HttpRequest, file_id: str) -> FileResponse | JsonResponse:
    file = File.objects.filter(id=file_id).first()
    if file is None or not can_read_file(request.user, file):
        return JsonResponse({"error": "Not found"}, status=404)   # 404, not 403: don't confirm the file exists

    # nosniff and sandbox: an uploaded HTML or SVG never runs as this site
    return FileResponse(uploads(request).open(file.id), content_type=file.type,
                        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})
# endregion
