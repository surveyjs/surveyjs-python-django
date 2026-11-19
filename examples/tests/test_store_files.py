"""Store Files Separately: the whole batch is checked before a byte is stored, types come from the bytes, names may
be non-ASCII, downloads can't run as the site, and a signed-out download is a 404."""

import re
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from examples.models import File
from examples.tests.helpers import ApiClient, SandboxTestCase, asgi_client, body

PNG = (settings.BASE_DIR / "shared" / "samples" / "work-order-scan.png").read_bytes()
PDF = b"%PDF-1.4\n% Demo receipt\n%%EOF\n"
HTML = b"<!DOCTYPE html><script>alert(document.cookie)</script>"
BIG = PNG + b"\0" * (5 * 1024 * 1024)


def upload(api: ApiClient, *files: tuple[str, bytes, str], field: str = "files[]", user: str | None = "alice"):
    return api.post("/api/files", data={field: [SimpleUploadedFile(name, content, type) for name, content, type in files]}, user=user)


def downloaded(response) -> bytes:
    """A FileResponse's bytes. Reading them to the end closes the response and its file (the test client's
    wrapper): closing it again would close the test's database connection too."""
    return b"".join(response.streaming_content)


class StoreFilesTests(TestCase):
    def setUp(self) -> None:
        self.api = ApiClient(self.client)

    def test_a_batch_is_stored_in_order_and_downloads_the_same_bytes(self) -> None:
        r = upload(self.api, ("one.pdf", PDF, "application/pdf"), ("two.png", PNG, "image/png"))
        self.assertEqual(r.status_code, 200)
        ids = r.json()
        self.assertEqual(len(ids), 2)
        for id, content, type in ((ids[0], PDF, "application/pdf"), (ids[1], PNG, "image/png")):
            d = self.api.get(f"/api/files/{id}")
            self.assertEqual((d.status_code, downloaded(d), d["Content-Type"]), (200, content, type))
            self.assertTrue((Path(settings.DATA_DIR) / "files" / id).is_file())   # stored by id, no extension

    def test_one_bad_file_refuses_the_whole_batch(self) -> None:
        before = File.objects.count()
        for files, message in (
            ([("ok.png", PNG, "image/png"), ("page.png", HTML, "image/png")], "page.png is not a PNG, JPEG, WebP, GIF or PDF file"),
            ([("ok.png", PNG, "image/png"), ("big.png", BIG, "image/png")], "Each file must be 5 MB or less"),
        ):
            self.assertEqual(body(upload(self.api, *files)), (422, {"error": message}))
        # PHP keeps only the last of several fields named "files"; the field is "files[]"
        self.assertEqual(body(upload(self.api, ("ok.png", PNG, "image/png"), field="files")),
                         (422, {"error": 'Upload one or more files in a field named "files[]"'}))
        self.assertEqual(File.objects.count(), before)

    def test_more_than_twenty_files_answer_400(self) -> None:
        r = upload(self.api, *[(f"{n}.png", PNG, "image/png") for n in range(21)])
        self.assertEqual(body(r), (400, {"error": "Bad request"}))

    def test_the_type_comes_from_the_bytes_and_the_name_may_be_cyrillic(self) -> None:
        [id] = upload(self.api, ("квитанция.png", PNG, "text/html")).json()
        file = File.objects.get(id=id)
        self.assertEqual((file.name, file.type), ("квитанция.png", "image/png"))

    def test_an_html_file_is_served_with_nosniff_and_sandbox(self) -> None:
        # The upload refuses HTML, so put one in place the way another code path might have stored it
        File.objects.create(id="html-file", name="page.html", type="text/html")
        folder = Path(settings.DATA_DIR) / "files"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "html-file").write_bytes(HTML)
        d = self.api.get("/api/files/html-file")
        self.assertEqual((d.status_code, downloaded(d)), (200, HTML))
        self.assertTrue(d["Content-Type"].startswith("text/html"))
        self.assertEqual((d["X-Content-Type-Options"], d["Content-Security-Policy"]), ("nosniff", "sandbox"))

    def test_signed_out_and_unknown_downloads_answer_404(self) -> None:
        [id] = upload(self.api, ("a.png", PNG, "image/png")).json()
        self.assertEqual(body(self.api.get(f"/api/files/{id}", user=None)), (404, {"error": "Not found"}))
        self.assertEqual(body(self.api.get("/api/files/no-such-file")), (404, {"error": "Not found"}))


def multipart(files: list[tuple[str, str, bytes]]) -> tuple[bytes, str]:
    boundary = "surveyjs-test-boundary"
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
             f"Content-Type: image/png\r\n\r\n".encode() + content + b"\r\n" for field, name, content in files]
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


@override_settings(DEMO_MODE=True)
class DemoUploadTests(SandboxTestCase):
    def test_the_demo_caps_every_upload_at_5_mb_first(self) -> None:
        async def run() -> list:
            results = []
            async with asgi_client(cookies={"demo_user": "alice"}) as client:
                for files, path in (([("files[]", "page.png", HTML), ("files[]", "big.png", BIG)], "/api/files"),
                                    ([("scan", "big.png", BIG)], "/api/work-orders/extract"),
                                    ([("files[]", "ok.png", PNG), ("files[]", "page.png", HTML)], "/api/files"),
                                    ([("files[]", "ok.png", PNG)], "/api/files")):
                    content, type = multipart(files)
                    r = await client.post(path, content=content, headers={"Content-Type": type})
                    results.append((r.status_code, r.json()))
                return [results, client.cookies.get("demo_sid")]
        results, sid = async_to_sync(run)()
        self.assertEqual(results[:2], [(413, {"error": "Files over 5 MB are not accepted on the demo"})] * 2)
        self.assertEqual(results[2][0], 422)
        self.assertEqual(results[3][0], 200)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", sid))
        [id] = results[3][1]
        self.assertTrue((Path(settings.DATA_DIR) / "sandbox" / sid / id).is_file())   # the visitor's uploads folder
