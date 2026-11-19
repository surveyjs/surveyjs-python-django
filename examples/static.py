"""Demo only: serves /shared/client/, /shared/definitions/, /shared/samples/ and /shared/ui/ (the shared client
modules, the definitions, the sample files and the page UI), and Django's /static/ (the committed site.css).

WhiteNoise, given exactly these four folders: nothing else under shared/ is reachable, and a path with .. never
leaves them. It sends Content-Type from its own table (.js and .mjs as text/javascript, .svg as image/svg+xml,
.woff2 as font/woff2), not from Python's mimetypes, which reads the Windows registry and can say text/plain for
a module. Sits right after SecurityMiddleware.

Under ASGI it also hands file responses (its own, and the FileResponse of store-files' downloads) to the server as
an async iterator, read chunk by chunk on a worker thread: Django's FileResponse streams a sync iterator, which
Django's ASGI handler would read whole on a thread, with a warning.
"""

import asyncio
import warnings
from collections.abc import AsyncIterator, Iterable

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.conf import settings
from whitenoise.middleware import WhiteNoiseMiddleware

SHARED_FOLDERS = ("client", "definitions", "samples", "ui")


class SharedFilesMiddleware(WhiteNoiseMiddleware):
    # WhiteNoise's middleware is sync only, which under ASGI would move every request onto Django's one thread for
    # sync code: this one answers in the mode of what it wraps
    sync_capable = True
    async_capable = True

    def __init__(self, get_response=None, settings=settings):
        with warnings.catch_warnings():   # STATIC_ROOT exists once collectstatic has run (the image); until then
            warnings.filterwarnings("ignore", "No directory at", UserWarning)   # static/ is served as it is
            super().__init__(get_response, settings)
        for folder in SHARED_FOLDERS:
            self.add_files(str(settings.BASE_DIR / "shared" / folder), prefix=f"shared/{folder}/")
        self.async_mode = iscoroutinefunction(get_response)
        if self.async_mode:
            markcoroutinefunction(self)

    def __call__(self, request):
        if self.async_mode:
            return self._acall(request)
        return super().__call__(request)

    async def _acall(self, request):
        static_file = self.find_file(request.path_info) if self.autorefresh else self.files.get(request.path_info)
        response = self.serve(static_file, request) if static_file is not None else await self.get_response(request)
        if response.streaming and not response.is_async:
            response.streaming_content = _read_on_a_thread(response.streaming_content)
        return response


async def _read_on_a_thread(chunks: Iterable[bytes]) -> AsyncIterator[bytes]:
    iterator = iter(chunks)
    while (chunk := await asyncio.to_thread(next, iterator, None)) is not None:
        yield chunk
