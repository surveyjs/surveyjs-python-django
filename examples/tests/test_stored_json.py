"""JSON is stored exactly as it arrives: the contract's round-trip document through every storing endpoint, read
back with the ORM, and the JSON that Python accepts but JSON doesn't (NaN, Infinity) refused."""

import json

from asgiref.sync import async_to_sync
from django.test import TestCase, TransactionTestCase

from examples.integration.stored_json import dumps
from examples.models import Claim, Form, Progress, Response, VariablePreset
from examples.tests.helpers import ROUNDTRIP, ApiClient, MockService, Socket, answer, switched


class StoredJsonTests(TestCase):
    def setUp(self) -> None:
        self.api = ApiClient(self.client)

    def test_save_response(self) -> None:
        r = self.api.post("/api/responses", json_body={"formId": "roundtrip", "data": ROUNDTRIP})
        self.assertEqual(r.status_code, 201)
        id = r.json()["id"]
        self.assertIsInstance(id, int)
        self.assertGreaterEqual(id, 1)
        self.assertEqual(json.loads(Response.objects.get(id=id).data), ROUNDTRIP)

    def test_stored_text_keeps_one_point_zero_and_readable_unicode(self) -> None:
        r = self.api.post("/api/responses", body=b'{"formId":"roundtrip","data":{"n":1.0,"h":"na\\u00efve"}}')
        self.assertEqual(Response.objects.get(id=r.json()["id"]).data, '{"n":1.0,"h":"naïve"}')

    def test_resume_progress(self) -> None:
        document = {"data": ROUNDTRIP, "uiState": {"currentPageName": "page2"}}
        self.assertEqual(self.api.put("/api/progress/roundtrip", json_body=document).status_code, 204)
        self.assertEqual(json.loads(Progress.objects.get(key="1:roundtrip").json), document)
        self.assertEqual(self.api.get("/api/progress/roundtrip").json(), document)

    def test_relational_storage(self) -> None:
        data = {**ROUNDTRIP, "customer_email": "a@example.com", "amount": 10.0}
        r = self.api.post("/api/claims", json_body={"data": data, "definitionVersion": "v2"})
        self.assertEqual(r.status_code, 201)
        response = Response.objects.get(id=r.json()["id"])
        self.assertEqual((json.loads(response.data), response.definition_version), (data, "v2"))
        claim = Claim.objects.get(response_id=response.id)
        self.assertEqual((claim.customer_email, float(claim.amount)), ("a@example.com", 10.0))

    def test_creator_load_save(self) -> None:
        self.assertEqual(self.api.put("/api/forms/roundtrip", json_body=ROUNDTRIP).status_code, 204)
        self.assertEqual(json.loads(Form.objects.get(key="roundtrip").json), ROUNDTRIP)
        self.assertEqual(self.api.get("/api/forms/roundtrip").json()["definition"], ROUNDTRIP)

    def test_variable_presets(self) -> None:
        presets = [{"name": "basic", "variables": {"extra": {}}}, {"name": "premium", "description": "", "variables": ROUNDTRIP}]
        self.assertEqual(self.api.put("/api/variable-presets/roundtrip", json_body=presets).status_code, 204)
        self.assertEqual(json.loads(VariablePreset.objects.get(key="roundtrip").json), presets)
        self.assertEqual(self.api.get("/api/variable-presets/roundtrip").json(), presets)

    def test_dashboard_returns_the_stored_documents(self) -> None:
        self.api.post("/api/responses", json_body={"formId": "roundtrip-dashboard", "data": ROUNDTRIP})
        r = self.api.get("/api/responses?formId=roundtrip-dashboard")
        self.assertTrue(r["Content-Type"].startswith("application/json"))
        self.assertEqual(r.json(), [ROUNDTRIP])

    def test_documents_are_text_never_json_fields(self) -> None:
        for model, field in ((Form, "json"), (Response, "data"), (Progress, "json"), (VariablePreset, "json")):
            self.assertEqual(model._meta.get_field(field).get_internal_type(), "TextField", f"{model.__name__}.{field}")

    def test_bodies_that_are_not_json_answer_400(self) -> None:
        bodies = [b'{"formId":"x","data":NaN}', b'{"formId":"x","data":Infinity}', b'{"formId":"x","data":-Infinity}',
                  b"{not json", b"", '{"formId":"x","data":"\xe9"}'.encode("latin-1")]
        for content in bodies:
            for method, path in (("POST", "/api/responses"), ("PUT", "/api/progress/x"), ("POST", "/api/claims"),
                                 ("PUT", "/api/forms/x"), ("PUT", "/api/variable-presets/x")):
                r = self.api.request(method, path, body=content)
                self.assertEqual((r.status_code, r.json()), (400, {"error": "The request body is not valid JSON"}),
                                 f"{method} {path} {content!r}")

    def test_dumps_refuses_nan(self) -> None:
        with self.assertRaises(ValueError):
            dumps(float("nan"))

    def test_validate_response_stores_what_it_validated(self) -> None:
        def valid(request):
            self.assertEqual(json.loads(request.content)["response"], ROUNDTRIP)   # the service gets the answers as sent
            return answer(200, {})(request)
        with switched(VALIDATE_RESPONSES=True), MockService(valid):
            r = self.api.post("/api/responses", json_body={"formId": "claim", "data": ROUNDTRIP})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(json.loads(Response.objects.get(id=r.json()["id"]).data), ROUNDTRIP)


class FillTogetherSaveTests(TransactionTestCase):
    def test_fill_together_saves_as_save_response_does(self) -> None:
        async def run() -> dict:
            socket = Socket("/ws/rooms/roundtrip-save?name=Ann")
            self.assertTrue(await socket.connect())
            self.assertEqual((await socket.receive())["type"], "init")
            await socket.send({"type": "complete", "data": ROUNDTRIP})
            completed = await socket.next_of("completed")
            await socket.close()
            return completed
        completed = async_to_sync(run)()
        saved = Response.objects.get(id=completed["id"], form_id="job-sheet")
        self.assertEqual(json.loads(saved.data), ROUNDTRIP)
