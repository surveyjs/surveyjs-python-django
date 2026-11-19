"""Run Server-Side Workflows: every row of the meta prompt's status mapping, and the checks made before the service
is called. The service is httpx2.MockTransport, through the one seam in examples/integration/http.py; the async views
run through Django's AsyncClient. Each case asserts the status, the body, what was stored, and that no answer reached
the log."""

import json
import logging
from contextlib import contextmanager
from typing import Any

import httpx2
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from examples.models import Claim, File, Form, Progress, Response, VariablePreset
from examples.tests.helpers import Handler, MockService, answer, switched

SERVICE = "http://surveyjs.test:3000"
PDF = b"%PDF-1.7\n% a filled claim\n%%EOF\n"
PNG = (settings.BASE_DIR / "shared" / "samples" / "work-order-scan.png").read_bytes()
SECRET = "Answer written on the paper form"   # must never reach the log


def timeout(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("timed out", request=request)


def refused(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ConnectError("connection refused", request=request)


UNEXPECTED = [
    answer(200, {"error": "schema is required"}),        # a 2xx alone never means success
    answer(200, content=b"{not json"),
    answer(500, {"error": "boom"}),
    answer(422, {"warnings": []}),
    answer(400, {"error": "INVALID_JSON"}),
]
FAILURES = [(timeout, 504, "SurveyJS service timed out"), (refused, 503, f"SurveyJS service is not running at {SERVICE}")]
CLAIM = {"customer_email": "valid@example.com", "amount": 120, "incident": "theft", "details": SECRET}
DEFINITION = {"elements": [{"type": "text", "name": "q1", "title": SECRET}]}
EXTRACTED = {"data": {"customer": SECRET, "hours": None}, "confidence": [{"fieldName": "customer", "value": SECRET,
             "confidence": 0.42, "flagged": True}], "uniqueId": "WO-1001"}


class ServiceTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.enterClassContext(switched(VALIDATE_RESPONSES=True, LINT_DEFINITIONS=True, SURVEYJS_SERVICE_URL=SERVICE))

    def setUp(self) -> None:
        self.async_client.cookies["demo_user"] = "alice"

    @contextmanager
    def service(self, handler: Handler):
        with MockService(handler) as service:
            yield service

    @contextmanager
    def logged(self):
        """The ERROR lines of examples.surveyjs while the block runs (empty when nothing was logged)."""
        logger = logging.getLogger("examples.surveyjs")
        records: list[str] = []
        handler = logging.Handler()
        handler.emit = lambda record: records.append(record.getMessage())   # type: ignore[method-assign]
        logger.addHandler(handler)
        try:
            yield records
        finally:
            logger.removeHandler(handler)

    async def post_json(self, path: str, payload: Any, method: str = "post") -> Any:
        return await getattr(self.async_client, method)(path, json.dumps(payload), content_type="application/json")

    async def counts(self) -> list[int]:
        return [await model.objects.acount() for model in (Form, Response, Progress, File, Claim, VariablePreset)]

    @staticmethod
    def json(response: Any) -> tuple[int, Any]:
        return response.status_code, json.loads(response.content)

    # ---------- validate-response

    async def test_validate_valid_answers_are_saved(self) -> None:
        before = await Response.objects.acount()
        with self.service(answer(200, {})) as service:
            r = await self.post_json("/api/responses", {"formId": "claim", "data": CLAIM})
        self.assertEqual(r.status_code, 201)
        self.assertIsInstance(json.loads(r.content)["id"], int)
        self.assertEqual(await Response.objects.acount(), before + 1)
        sent = json.loads(service.calls[0].content)
        self.assertEqual((service.calls[0].url.path, sent["response"]), ("/response", CLAIM))
        self.assertIn("elements", json.dumps(sent["schema"]))

    async def test_validate_errors_answer_400_and_save_nothing(self) -> None:
        errors = [{"name": "incident", "text": "Unknown choice"}]
        before = await Response.objects.acount()
        with self.service(answer(422, {"errors": errors})):
            r = await self.post_json("/api/responses", {"formId": "claim", "data": CLAIM})
        self.assertEqual(self.json(r), (400, {"errors": errors}))
        self.assertEqual(await Response.objects.acount(), before)

    async def test_validate_a_broken_definition_answers_502_and_is_logged(self) -> None:
        before = await Response.objects.acount()
        with self.service(answer(422, {"errors": [{"rule": "x"}], "warnings": []})), self.logged() as log:
            r = await self.post_json("/api/responses", {"formId": "claim", "data": CLAIM})
        self.assertEqual(self.json(r), (502, {"error": "The stored definition has errors"}))
        self.assertEqual(await Response.objects.acount(), before)
        self.assertTrue(any("unexpected answer from /response: 422" in line for line in log))
        self.assertFalse(any(SECRET in line for line in log))

    async def test_validate_anything_else_answers_502(self) -> None:
        for handler in UNEXPECTED:
            with self.subTest(handler=handler):
                before = await Response.objects.acount()
                with self.service(handler), self.logged() as log:
                    r = await self.post_json("/api/responses", {"formId": "claim", "data": CLAIM})
                self.assertEqual(self.json(r), (502, {"error": "SurveyJS service error"}))
                self.assertEqual(await Response.objects.acount(), before)
                self.assertTrue(log, "logged")

    async def test_validate_timeout_and_refused(self) -> None:
        for handler, status, message in FAILURES:
            with self.subTest(status=status):
                before = await Response.objects.acount()
                with self.service(handler):
                    r = await self.post_json("/api/responses", {"formId": "claim", "data": CLAIM})
                self.assertEqual(self.json(r), (status, {"error": message}))
                self.assertEqual(await Response.objects.acount(), before)

    async def test_validate_prechecks_never_call_the_service(self) -> None:
        before = await Response.objects.acount()
        with self.service(answer(200, {})) as service:
            for payload in ([], {"formId": 1, "data": CLAIM}, {"formId": "claim", "data": "answers"}, {"formId": "claim"}):
                r = await self.post_json("/api/responses", payload)
                self.assertEqual(self.json(r), (400, {"error": "Expected { formId, data } with an answers object"}))
            r = await self.post_json("/api/responses", {"formId": "no-such-form", "data": {}})
            self.assertEqual(self.json(r), (404, {"error": "Unknown form"}))
        self.assertEqual((service.calls, await Response.objects.acount()), ([], before))

    # ---------- lint-definition

    async def stored_form(self, key: str) -> Any:
        form = await Form.objects.filter(key=key).afirst()
        return json.loads(form.json) if form else None

    async def test_lint_clean_saves_and_answers_204(self) -> None:
        with self.service(answer(200, {})) as service:
            r = await self.post_json("/api/forms/lint-clean", DEFINITION, "put")
        self.assertEqual((r.status_code, r.content), (204, b""))
        self.assertEqual(await self.stored_form("lint-clean"), DEFINITION)
        self.assertEqual((service.calls[0].url.path, json.loads(service.calls[0].content)), ("/schema", DEFINITION))

    async def test_lint_warnings_save_and_answer_200(self) -> None:
        warnings = [{"rule": "property/unknown", "message": "someproperty"}]
        with self.service(answer(200, {"warnings": warnings})):
            r = await self.post_json("/api/forms/lint-warned", DEFINITION, "put")
        self.assertEqual(self.json(r), (200, {"warnings": warnings}))
        self.assertEqual(await self.stored_form("lint-warned"), DEFINITION)

    async def test_lint_errors_answer_422_and_keep_the_previous_version(self) -> None:
        with self.service(answer(200, {})):
            await self.post_json("/api/forms/lint-kept", {"title": "previous"}, "put")
        findings = {"errors": [{"rule": "expression/unknown-variable"}], "warnings": []}
        with self.service(answer(422, findings)):
            r = await self.post_json("/api/forms/lint-kept", DEFINITION, "put")
        self.assertEqual(self.json(r), (422, findings))
        self.assertEqual(await self.stored_form("lint-kept"), {"title": "previous"})

    async def test_lint_anything_else_answers_502_and_saves_nothing(self) -> None:
        for handler in [*UNEXPECTED, answer(422, {"errors": []}), answer(400, {"error": "INVALID_SCHEMA"}),
                        answer(200, {"warnings": [], "extra": 1})]:
            with self.subTest(handler=handler), self.service(handler):
                r = await self.post_json("/api/forms/lint-refused", DEFINITION, "put")
                self.assertEqual(self.json(r), (502, {"error": "SurveyJS service error"}))
                self.assertIsNone(await self.stored_form("lint-refused"))

    async def test_lint_timeout_and_refused(self) -> None:
        for handler, status, message in FAILURES:
            with self.subTest(status=status), self.service(handler):
                r = await self.post_json("/api/forms/lint-failed", DEFINITION, "put")
                self.assertEqual(self.json(r), (status, {"error": message}))
                self.assertIsNone(await self.stored_form("lint-failed"))

    async def test_lint_is_for_editors_and_never_calls_the_service_otherwise(self) -> None:
        with self.service(answer(200, {})) as service:
            for user in ("bob", "none"):
                self.async_client.cookies["demo_user"] = user
                r = await self.post_json("/api/forms/lint-denied", DEFINITION, "put")
                self.assertEqual(self.json(r), (403, {"error": "You don't have editor rights: only editors can change forms"}))
        self.assertEqual(service.calls, [])

    # ---------- server-pdf and the blank work order

    async def first_claim(self) -> int:
        return (await Response.objects.filter(form_id="claim", definition_version="v1").afirst()).id

    async def test_pdf_bytes_pass_through_with_the_contract_headers(self) -> None:
        claim = await self.first_claim()
        with self.service(answer(200, content=PDF, content_type="application/pdf")) as service:
            r = await self.async_client.get(f"/api/claims/{claim}/pdf")
            blank = await self.async_client.get("/api/work-orders/blank.pdf")
        self.assertEqual((r.status_code, r.content, r["Content-Type"]), (200, PDF, "application/pdf"))
        self.assertEqual(r["Content-Disposition"], f'inline; filename="claim-{claim}.pdf"')
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertEqual((service.calls[0].url.path, set(json.loads(service.calls[0].content))), ("/pdf", {"schema", "response"}))
        self.assertEqual((blank.status_code, blank.content), (200, PDF))
        self.assertEqual(blank["Content-Disposition"], 'attachment; filename="work-order.pdf"')
        self.assertEqual(blank["Cache-Control"], "private, no-store")
        self.assertEqual(set(json.loads(service.calls[1].content)), {"schema"})

    async def test_pdf_anything_else_answers_502(self) -> None:
        claim = await self.first_claim()
        for handler in [*UNEXPECTED, answer(200, content=b"not a pdf", content_type="application/pdf"),
                        answer(200, content=PDF, content_type="application/octet-stream"),
                        answer(422, {"errors": [], "warnings": []})]:
            for path in (f"/api/claims/{claim}/pdf", "/api/work-orders/blank.pdf"):
                with self.subTest(path=path, handler=handler), self.service(handler):
                    self.assertEqual(self.json(await self.async_client.get(path)), (502, {"error": "SurveyJS service error"}))

    async def test_pdf_timeout_and_refused(self) -> None:
        claim = await self.first_claim()
        for handler, status, message in FAILURES:
            for path in (f"/api/claims/{claim}/pdf", "/api/work-orders/blank.pdf"):
                with self.subTest(path=path, status=status), self.service(handler):
                    self.assertEqual(self.json(await self.async_client.get(path)), (status, {"error": message}))

    async def test_pdf_prechecks_never_call_the_service(self) -> None:
        unknown_version = await Response.objects.acreate(form_id="claim", definition_version="v9", data="{}",
                                                         created_at="2026-11-19T09:00:00Z")
        with self.service(answer(200, content=PDF, content_type="application/pdf")) as service:
            self.assertEqual(self.json(await self.async_client.get("/api/claims/999999/pdf")), (404, {"error": "Unknown claim"}))
            self.assertEqual(self.json(await self.async_client.get(f"/api/claims/{unknown_version.id}/pdf")),
                             (409, {"error": "The schema version for this claim is unavailable"}))
            await Form.objects.filter(key="work-order").adelete()
            self.assertEqual(self.json(await self.async_client.get("/api/work-orders/blank.pdf")),
                             (404, {"error": "Unknown work order form"}))
        self.assertEqual(service.calls, [])

    # ---------- extract-from-paper

    async def extract(self, content: bytes = PNG, field: str = "scan") -> Any:
        return await self.async_client.post("/api/work-orders/extract", {field: SimpleUploadedFile("scan.png", content, "image/png")})

    async def test_extract_answers_the_draft_and_saves_nothing(self) -> None:
        before = await self.counts()
        with self.service(answer(200, EXTRACTED)) as service, self.logged() as log:
            r = await self.extract()
        self.assertEqual(self.json(r), (200, {"answers": EXTRACTED["data"], "confidence": EXTRACTED["confidence"],
                                             "uniqueId": "WO-1001"}))
        self.assertEqual((await self.counts(), log), (before, []))
        sent = json.loads(service.calls[0].content)   # JSON with base64, never multipart
        self.assertEqual((service.calls[0].headers["content-type"], set(sent)), ("application/json", {"schema", "document"}))
        self.assertTrue(sent["document"].startswith("iVBOR"))

    async def test_extract_recognized_failures(self) -> None:
        for status, code, message in ((400, "INVALID_DOCUMENT", "The file is not a PDF, PNG, JPEG, WebP or GIF document"),
                                      (503, "AI_NOT_CONFIGURED", "The SurveyJS service has no AI provider configured"),
                                      (502, "EXTRACTION_FAILED", "Could not extract the response from the document")):
            with self.subTest(code=code), self.service(answer(status, {"error": code})):
                before = await self.counts()
                self.assertEqual(self.json(await self.extract()), (status, {"error": message}))
                self.assertEqual(await self.counts(), before)

    async def test_extract_anything_else_answers_502_logged_by_status_only(self) -> None:
        for handler in [*UNEXPECTED, answer(200, {"data": [SECRET]}), answer(200, {"confidence": []}),
                        answer(422, {"errors": [], "warnings": []}), answer(400, {"error": "EXTRACTION_FAILED"})]:
            with self.subTest(handler=handler), self.service(handler), self.logged() as log:
                before = await self.counts()
                self.assertEqual(self.json(await self.extract()), (502, {"error": "SurveyJS service error"}))
                self.assertEqual(await self.counts(), before)
                self.assertTrue(any("unexpected answer from /extract" in line for line in log))
                self.assertFalse(any(SECRET in line for line in log))

    async def test_extract_timeout_and_refused(self) -> None:
        for handler, status, message in FAILURES:
            with self.subTest(status=status), self.service(handler):
                self.assertEqual(self.json(await self.extract()), (status, {"error": message}))

    async def test_extract_prechecks_never_call_the_service(self) -> None:
        with self.service(answer(200, EXTRACTED)) as service:
            self.assertEqual(self.json(await self.extract(field="document")), (400, {"error": 'Upload the scan in a field named "scan"'}))
            r = await self.async_client.post("/api/work-orders/extract", {"scan": "not a file"})
            self.assertEqual(self.json(r), (413, {"error": "The scan must be a file of 5 MB or less"}))
            self.assertEqual(self.json(await self.extract(PNG + b"\0" * (5 * 1024 * 1024))),
                             (413, {"error": "The scan must be a file of 5 MB or less"}))
            self.assertEqual(self.json(await self.extract(b"Not a scan: plain text in a file named .png\n")),
                             (400, {"error": "The file is not a PDF, PNG, JPEG, WebP or GIF document"}))
        self.assertEqual(service.calls, [])
