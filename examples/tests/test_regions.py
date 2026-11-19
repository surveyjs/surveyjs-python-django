"""The comments on data-corrupting pitfalls are inside the regions the docs show, the regions hold no plumbing, the
view modules stand alone, and nothing but config/settings.py reads the environment."""

import re

from django.conf import settings
from django.test import SimpleTestCase

from demo.code_panel import regions_in
from examples.management.commands.surveyjs_check import PLUMBING, check

PITFALLS = [
    ("examples/views/save_response.py", "save-response.server", ["The raw body, not request.POST", "{} stays {}"]),
    ("examples/views/resume_progress.py", "resume-progress.server", ["The raw body, not request.POST", "{} stays {}"]),
    ("examples/views/relational_storage.py", "relational-storage.server", ["The raw body, not request.POST", "keys come from valueName"]),
    ("examples/views/creator_load_save.py", "creator-load-save.server", ["The raw body, not request.POST", "{} stays {}"]),
    ("examples/views/variable_presets.py", "variable-presets.server", ["The raw body, not request.POST", "{} stays {}"]),
    ("examples/views/validate_response.py", "validate-response.server", ["The raw body, not request.POST", "fail closed"]),
    ("examples/views/lint_definition.py", "lint-definition.server", ["keeps {} as {}", "fail closed"]),
    ("examples/views/store_files.py", "store-files.server", ['"files[]"', 'Not request.FILES["files[]"]: that is only the last file',
                                                             "by the bytes, never the client's type", "never by the client"]),
    ("examples/views/store_files.py", "store-files.download", ["404, not 403", "nosniff and sandbox"]),
    ("examples/views/choices_from_web.py", "choices-from-web.server", ["the browser can't call a service without CORS"]),
    ("examples/views/dashboard.py", "dashboard.server", ["as stored", "ISO 8601 UTC strings compare as dates"]),
    ("examples/views/extract_from_paper.py", "extract-from-paper.server", ["JSON with base64", "logged by status only"]),
    ("examples/views/load_definition_variables_data.py", "load-definition-variables-data.server", ["json_script"]),
    ("examples/consumers/fill_together.py", "fill-together.server", ["your session check", "refused handshake"]),
    ("examples/consumers/edit_together.py", "edit-together.server", ["editing together is for editors", "refused handshake"]),
]


class RegionTests(SimpleTestCase):
    def test_the_pitfall_comments_are_inside_the_regions(self) -> None:
        for path, id, comments in PITFALLS:
            region = regions_in(path).get(id)
            self.assertIsNotNone(region, f"{path} has sjs:{id}")
            for comment in comments:
                self.assertIn(comment, region.code, f"sjs:{id} explains: {comment}")

    def test_server_regions_show_no_plumbing(self) -> None:
        for folder in ("views", "consumers"):
            for path in sorted((settings.BASE_DIR / "examples" / folder).glob("*.py")):
                for id, found in regions_in(path.relative_to(settings.BASE_DIR).as_posix()).items():
                    for token in PLUMBING:
                        self.assertNotIn(token, found.code, f"sjs:{id} shows {token}")

    def test_view_modules_stand_alone(self) -> None:
        for path in sorted((settings.BASE_DIR / "examples" / "views").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"(?m)^from examples\.views|^import examples\.views|^from \. ", f"{path.name} imports a view module")
            if path.name != "__init__.py":
                self.assertTrue(source.startswith('"""'), f"{path.name} starts with what it serves")

    def test_no_module_reads_the_environment_but_settings(self) -> None:
        allowed = {"config/settings.py", "config/settings_test.py", "config/asgi.py", "config/wsgi.py",
                   "examples/management/commands/serve.py", "examples/management/commands/contract.py"}
        for folder in ("config", "examples", "demo"):
            for path in sorted((settings.BASE_DIR / folder).rglob("*.py")):
                relative = path.relative_to(settings.BASE_DIR).as_posix()
                if relative not in allowed and "/tests/" not in relative:
                    self.assertNotRegex(path.read_text(encoding="utf-8"), r"os\.environ|getenv", relative)

    def test_the_check_command_passes(self) -> None:
        self.assertEqual(check(complete=True), [])

    def test_no_raw_sql_in_example_code(self) -> None:
        for path in sorted((settings.BASE_DIR / "examples" / "views").glob("*.py")):
            self.assertIsNone(re.search(r"cursor\(|\.raw\(|RawSQL|\.extra\(", path.read_text(encoding="utf-8")), path.name)
