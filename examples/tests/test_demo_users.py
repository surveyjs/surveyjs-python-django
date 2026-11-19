"""The demo users: each page signs in as a user it offers, the API reads the cookie as it is, Bob's saves answer
403 with the edit-forms message, signed out the progress endpoints answer 401, and Alice's permission is Django's."""

from django.test import TestCase

from examples.models import Progress, User
from examples.tests.helpers import ApiClient, body, page_config


def demo_user_cookie(response) -> str | None:
    morsel = response.cookies.get("demo_user")
    return morsel.OutputString() if morsel else None


class DemoUserTests(TestCase):
    def setUp(self) -> None:
        self.api = ApiClient(self.client)

    def test_a_page_that_offers_the_user_keeps_it_any_other_signs_in_as_its_default(self) -> None:
        kept = self.api.get("/examples/resume-progress", user="bob")
        self.assertEqual(page_config(kept.content.decode())["demoUser"], "bob")
        self.assertIsNone(demo_user_cookie(kept))

        reset = self.api.get("/examples/save-response", user="bob")
        self.assertEqual(page_config(reset.content.decode())["demoUser"], "alice")
        cookie = demo_user_cookie(reset)
        self.assertTrue(cookie.startswith("demo_user=alice;"))
        self.assertIn("samesite=lax", cookie.lower())
        self.assertNotIn("httponly", cookie.lower())   # host.js writes it back on focus

        self.assertEqual(page_config(self.api.get("/examples/creator-load-save", user="none").content.decode())["demoUser"], "alice")
        config = page_config(self.api.get("/examples/dashboard", user=None).content.decode())
        self.assertEqual(config["user"], {"key": "alice", "name": "Alice Martin", "plan": "premium", "isEditor": True})

    def test_claim_signs_in_like_its_example_page(self) -> None:
        bob = self.api.get("/claim", user="bob").content.decode()
        self.assertIn('"plan": "basic"', bob)
        signed_out = self.api.get("/claim", user=None)
        html = signed_out.content.decode()
        self.assertIn('<script id="form-variables" type="application/json">{"user": {"name": "Alice Martin", "plan": "premium"}}</script>', html)
        self.assertTrue(demo_user_cookie(signed_out).startswith("demo_user=alice;"))

    def test_the_switch_appears_only_where_the_user_changes_the_result(self) -> None:
        for slug, labels in (
            ("load-definition-variables-data", ["Alice (premium)", "Bob (basic)"]),
            ("resume-progress", ["Alice", "Bob"]),
            ("creator-load-save", ["Alice (can save schemas)", "Bob (cannot save schemas)"]),
        ):
            html = self.api.get(f"/examples/{slug}").content.decode()
            self.assertIn('id="demo-user"', html, slug)
            for label in labels:
                self.assertIn(f">{label}</option>", html, f"{slug}: {label}")
        for slug in ("save-response", "store-files", "dashboard", "variable-presets", "fill-together"):
            self.assertNotIn('id="demo-user"', self.api.get(f"/examples/{slug}").content.decode(), slug)

    def test_bob_and_signed_out_saves_answer_403(self) -> None:
        message = "You don't have editor rights: only editors can change forms"
        for user in ("bob", None, "none", "mallory"):
            for path in ("/api/forms/support", "/api/variable-presets/support"):
                self.assertEqual(body(self.api.put(path, json_body=[], user=user)), (403, {"error": message}), f"{path} as {user}")

    def test_editing_is_a_django_permission_of_the_editors_group(self) -> None:
        alice, bob = User.objects.get(username="alice"), User.objects.get(username="bob")
        self.assertTrue(alice.has_perm("examples.edit_forms"))
        self.assertFalse(bob.has_perm("examples.edit_forms"))
        self.assertEqual(list(alice.groups.values_list("name", flat=True)), ["Editors"])
        self.assertFalse(alice.has_usable_password())

    def test_progress_is_per_user_and_answers_401_signed_out(self) -> None:
        for method, message in (("GET", "Sign in to load progress"), ("PUT", "Sign in to save progress"),
                                ("DELETE", "Sign in to clear progress")):
            r = self.api.request(method, "/api/progress/onboarding", user=None, json_body={} if method == "PUT" else None)
            self.assertEqual(body(r), (401, {"error": message}))
        self.api.put("/api/progress/demo-users", json_body={"data": {"who": "alice"}})
        self.assertEqual(self.api.get("/api/progress/demo-users", user="bob").content, b"null")
        alice = User.objects.get(username="alice")
        self.assertTrue(Progress.objects.filter(key=f"{alice.pk}:demo-users").exists())
        self.assertEqual(self.api.get("/api/progress/onboarding", user="mallory").status_code, 401)
