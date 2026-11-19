"""Under /api/ every error is { error } with its status, including Django's own answers, which would otherwise be
HTML pages: with DEBUG on (Django's technical pages) and off. Outside /api/ the errors stay HTML."""

from unittest import mock

from asgiref.sync import async_to_sync
from django.test import TestCase, TransactionTestCase, override_settings

from examples.tests.helpers import ApiClient, SandboxTestCase, asgi_client, body

TOO_BIG = 24 * 1024 * 1024 + 1


class ErrorShapeTests(TestCase):
    def setUp(self) -> None:
        self.api = ApiClient(self.client)

    def check_all(self) -> None:
        api = self.api
        # 400: a body that isn't JSON, a form post to a JSON endpoint, a bad query parameter, a wrong envelope
        self.assertEqual(body(api.post("/api/responses", body=b"{not json")), (400, {"error": "The request body is not valid JSON"}))
        self.assertEqual(body(api.post("/api/responses", body=b"formId=contact&data=x", content_type="application/x-www-form-urlencoded")),
                         (400, {"error": "The request body is not valid JSON"}))
        self.assertEqual(body(api.get("/api/responses?formId=feedback&limit=abc")), (400, {"error": "limit and offset must be whole numbers"}))
        self.assertEqual(body(api.post("/api/responses", json_body={"formId": "contact"})), (400, {"error": "Expected { formId, data }"}))
        # 401, 403
        self.assertEqual(body(api.get("/api/progress/onboarding", user=None)), (401, {"error": "Sign in to load progress"}))
        self.assertEqual(body(api.put("/api/forms/support", json_body={}, user="bob")),
                         (403, {"error": "You don't have editor rights: only editors can change forms"}))
        # 404: the resolver's, a trailing slash (APPEND_SLASH doesn't redirect it), a view's own
        self.assertEqual(body(api.get("/api/no-such-thing")), (404, {"error": "Not found"}))
        self.assertEqual(body(api.get("/api/offices/")), (404, {"error": "Not found"}))
        self.assertEqual(body(api.get("/api/claims/abc/pdf")), (404, {"error": "Not found"}))
        self.assertEqual(body(api.get("/api/forms/no-such-form")), (404, {"error": "Unknown form"}))
        # 405 with Allow naming every method of the path
        r = api.request("PATCH", "/api/progress/onboarding")
        self.assertEqual((body(r), r["Allow"]), ((405, {"error": "Method not allowed"}), "DELETE, GET, PUT"))
        r = api.put("/api/offices")
        self.assertEqual((body(r), r["Allow"]), ((405, {"error": "Method not allowed"}), "GET"))
        # 413: a JSON body over DATA_UPLOAD_MAX_MEMORY_SIZE (Django's RequestDataTooBig)
        self.assertEqual(body(api.post("/api/responses", body=b" " * TOO_BIG)), (413, {"error": "The request body is too large"}))
        # 422
        self.assertEqual(body(api.post("/api/files", data={"other": "x"})),
                         (422, {"error": 'Upload one or more files in a field named "files[]"'}))
        # 500: a view that raises, logged with its traceback
        with mock.patch("examples.views.choices_from_web.Office.objects.filter", side_effect=RuntimeError("the database is on fire")), \
                self.assertLogs("examples", "ERROR") as logs:
            self.assertEqual(body(api.get("/api/offices")), (500, {"error": "Internal server error"}))
        self.assertIn("the database is on fire", "\n".join(logs.output))

    def test_with_debug_off(self) -> None:
        self.check_all()

    @override_settings(DEBUG=True)
    def test_with_debug_on(self) -> None:
        self.check_all()

    def test_pages_get_html_errors(self) -> None:
        r = self.api.get("/examples/no-such-example")
        self.assertEqual(r.status_code, 404)
        self.assertTrue(r["Content-Type"].startswith("text/html"))
        r = self.api.get("/examples/edit-together?form=bad%20id")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Invalid form ID", r.content.decode())


class DemoLimitTests(SandboxTestCase):
    @override_settings(DEMO_MODE=True)
    def test_429_demo_ai_limit(self) -> None:
        async def run() -> list:
            async with asgi_client() as client:
                await client.get("/api/offices")   # takes demo_sid from the server
                payload = {"strings": [], "from": "en", "to": "de"}
                statuses = [(await client.post("/api/translate", json=payload)).status_code for _ in range(20)]
                last = await client.post("/api/translate", json=payload)
                return [statuses, last.status_code, last.json()]
        statuses, status, error = async_to_sync(run)()
        self.assertEqual(statuses, [501] * 20)
        self.assertEqual((status, error), (429, {"error": "The demo allows 20 AI calls per visitor per day"}))


class BodyLimitTests(TransactionTestCase):
    """The ASGI body limit caps every request, files included, also a chunked one without Content-Length."""

    def test_413_before_django_reads_the_body(self) -> None:
        async def run() -> list:
            async def chunks():
                for _ in range(25):
                    yield b" " * (1024 * 1024)
            async with asgi_client() as client:
                declared = await client.post("/api/files", content=b"x" * TOO_BIG, headers={"Content-Type": "multipart/form-data; boundary=x"})
                chunked = await client.post("/api/responses", content=chunks(), headers={"Content-Type": "application/json"})
                return [declared.status_code, declared.json(), chunked.status_code, chunked.json()]
        self.assertEqual(async_to_sync(run)(), [413, {"error": "The request body is too large"}] * 2)
