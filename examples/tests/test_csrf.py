"""CSRF: the API takes POST, PUT and DELETE without a token (the shared client sends none), and a page still
refuses a POST without one. Django's test client skips CSRF checks unless asked, so these ask."""

from django.test import Client, TestCase

from examples.tests.helpers import ApiClient


class CsrfTests(TestCase):
    def setUp(self) -> None:
        self.api = ApiClient(Client(enforce_csrf_checks=True))

    def test_the_api_needs_no_token(self) -> None:
        self.assertEqual(self.api.post("/api/responses", json_body={"formId": "contact", "data": {}}).status_code, 201)
        self.assertEqual(self.api.put("/api/progress/csrf", json_body={"data": {}}).status_code, 204)
        self.assertEqual(self.api.delete("/api/progress/csrf").status_code, 204)
        self.assertEqual(self.api.put("/api/forms/csrf", json_body={}).status_code, 204)

    def test_a_page_post_still_needs_one(self) -> None:
        r = self.api.post("/examples/save-response", body=b"x=1", content_type="application/x-www-form-urlencoded")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r["Content-Type"].startswith("text/html"))
