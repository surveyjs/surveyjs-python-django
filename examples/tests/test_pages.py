"""The pages: every example renders with its module, the import map and window.SURVEYJS_PAGE; inline JSON can't end
its <script>; the layout's ids and blocks are where the reference puts them; /shared serves only its four folders
with JavaScript MIME types; and behind a TLS proxy the page's URLs are https and wss."""

import asyncio
import json
import re
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings
from django.test import TestCase, TransactionTestCase, override_settings
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

import httpx2
from demo.manifest import read_manifest
from examples.frontend import HIGHLIGHT_LANGUAGES
from examples.models import Form
from examples.tests.helpers import DOCS, ApiClient, asgi_client, page_config

STEPS = read_manifest()["steps"]
SLUGS = [step["slug"] for step in STEPS]
START_OVER = ["save-response", "load-definition-variables-data", "resume-progress", "store-files", "choices-from-web",
              "async-functions", "relational-storage", "validate-response", "extract-from-paper"]
SPECIFIERS = ["survey-core", "survey-core/collaboration", "survey-core/i18n", "survey-js-ui", "survey-creator-core",
              "survey-creator-core/collaboration", "survey-creator-js", "survey-analytics", "chart.js", "@kurkle/color",
              "lodash/debounce", "highlight.js/lib/core"]


def import_map(html: str) -> dict:
    return json.loads(re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1))


def stylesheets(html: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="([^"]+)">', html)


class PageTests(TestCase):
    def setUp(self) -> None:
        self.api = ApiClient(self.client)

    def html(self, path: str, **kwargs) -> str:
        r = self.api.get(path, **kwargs)
        self.assertEqual(r.status_code, 200, path)
        return r.content.decode()

    def test_every_example_renders_its_module_after_the_shared_ui_with_the_import_map_and_the_page_config(self) -> None:
        version = read_manifest()["surveyjsVersion"]
        for step in STEPS:
            html = self.html(step["page"])
            scripts = re.findall(r'<script type="module" src="([^"]+)">', html)
            self.assertEqual(scripts, ["/shared/ui/code-highlight.js", "/shared/ui/page-tabs.js", f"/{step['files']['client']}"])
            imports = import_map(html)["imports"]
            for specifier in SPECIFIERS:
                self.assertIn(specifier, imports, f"{step['slug']}: {specifier}")
            self.assertEqual(imports["survey-core"], f"https://unpkg.com/survey-core@{version}/fesm/survey-core.mjs")
            self.assertLess(html.index('<script type="importmap">'), html.index('<script type="module"'))
            config = page_config(html)
            self.assertEqual((config["slug"], config["version"]), (step["slug"], version))
            self.assertEqual(list(config["relay"]), ["fill", "edit"])
            self.assertEqual(config["relay"]["fill"]["port"], 8000)
            for role in (role for role in step["files"] if role.startswith("definition")):
                self.assertTrue(config[role], f"{step['slug']}: {role}")
            self.assertIn(f"<title>{step['title']} · SurveyJS + Django</title>", html)

    def test_the_import_map_has_every_language_code_highlight_imports(self) -> None:
        source = (settings.BASE_DIR / "shared" / "ui" / "code-highlight.js").read_text(encoding="utf-8")
        imported = re.findall(r"from 'highlight\.js/lib/languages/([a-z]+)'", source)
        self.assertEqual(sorted(imported), sorted(HIGHLIGHT_LANGUAGES))
        self.assertIn("java", imported)
        imports = import_map(self.html("/examples/save-response"))["imports"]
        for language in imported:
            self.assertEqual(imports[f"highlight.js/lib/languages/{language}"],
                             f"https://unpkg.com/@highlightjs/cdn-assets@11.12.0/es/languages/{language}.min.js")

    def test_a_script_tag_in_a_stored_definition_or_a_query_value_cant_end_the_inline_script(self) -> None:
        definition = {"title": "</script><script>alert(1)</script>", "elements": [{"type": "text", "name": "q1", "title": "é & <b>"}]}
        Form.objects.filter(key="work-order").update(json=json.dumps(definition))
        html = self.html("/examples/extract-from-paper")
        self.assertNotIn("</script><script>alert(1)", html)
        self.assertIn("\\u003C/script\\u003E\\u003Cscript\\u003Ealert(1)\\u003C/script\\u003E", html)
        self.assertEqual(page_config(html)["definition"], definition)
        record = self.html("/examples/fill-together?record=%3C%2Fscript%3E%3Cb%3E")
        self.assertNotIn("</script><b>", record)
        self.assertIn("&lt;/script&gt;&lt;b&gt;", record)

    def test_start_over_is_on_exactly_the_nine_pages_between_the_other_actions_and_the_component(self) -> None:
        for slug in SLUGS:
            html = self.html(f"/examples/{slug}")
            self.assertEqual('id="start-over"' in html, slug in START_OVER, slug)
            if slug in START_OVER:
                self.assertLess(html.index('id="start-over"'), html.index('id="component"'), slug)
        self.assertIn('id="start-over"', self.html("/claim"))
        self.assertIn('<button id="start-over" type="button" disabled', self.html("/examples/resume-progress"))

    def test_the_layout_ids_one_docs_link_and_about_where_the_reference_renders_it(self) -> None:
        ids = ["page-header", "side-panel", "panel-close", "panel-tabs", "panel-tabs-thumb", "hood", "panel-description", "try",
               "panel-requests", "readouts", "notes", "show-demo-requests", "clear-requests", "requests-empty", "requests",
               "panel-stored", "stored-updated", "stored", "main-tabs", "panel-toggle", "panel-dot", "page-tabs", "panel-demo",
               "component", "panel-code", "request-row", "stored-section", "note", "requests-count", "stored-dot"]
        for step in STEPS:
            html = self.html(f"/examples/{step['slug']}")
            for id in ids:
                self.assertIn(f'id="{id}"', html, f"{step['slug']}: #{id}")
            self.assertEqual(html.count(">Documentation</a>"), 1, step["slug"])
            self.assertIn(f'href="{DOCS}#{step["anchor"]}"', html)
            about = '<div class="space-y-2 text-sm text-gray-600">' in html
            self.assertEqual(about, step["slug"] == "extract-from-paper", f"{step['slug']}: the about block")
            self.assertEqual("require a developer license" in html, step["licence"].startswith("Commercial"), step["slug"])
            self.assertEqual(html.count("<details data-code-section open"), len(step["regions"]), f"{step['slug']}: one section per region")
            self.assertEqual('id="actions"' in html, step["slug"] != "dashboard", step["slug"])
        with override_settings(DEMO_MODE=True):
            for slug in ("fill-together", "edit-together"):
                self.assertIn("The invite link carries your sandbox ID", self.html(f"/examples/{slug}"), f"{slug} in demo mode")

    def test_the_code_tab_shows_python_regions_with_github_line_links(self) -> None:
        html = self.html("/examples/save-response")
        self.assertIn('<code class="language-python block !bg-transparent p-4">', html)
        self.assertIn("/blob/main/examples/views/save_response.py#L", html)
        self.assertIn("sjs:save-response.server", html)
        self.assertIn("sjs:save-response.client", html)
        self.assertIn("/blob/main/examples/consumers/fill_together.py#L", self.html("/examples/fill-together"))

    def test_the_catalog_the_pdf_loading_page_and_claim(self) -> None:
        catalog = self.html("/")
        self.assertIn("<title>Python Backend Integration with Django · SurveyJS</title>", catalog)
        self.assertIn("Step-by-Step Python Backend Integration with Django", catalog)
        self.assertIn("Build a Python Backend for&nbsp;Your SurveyJS Forms", catalog)
        self.assertIn(">Django integration guide</a>", catalog)
        self.assertEqual(catalog.count(">Run Example</a>"), 18)
        self.assertNotRegex(catalog, r"\bPHP\b|Laravel|FastAPI")
        self.assertIn("Generating the PDF...", self.html("/examples/server-pdf/loading"))
        claim = self.html("/claim")
        self.assertIn('window.FORM_DEFINITION = JSON.parse(document.getElementById("form-definition").textContent);', claim)
        self.assertIn('{"user": {"name": "Alice Martin", "plan": "premium"}}', claim)
        for path in ("/", "/examples/save-response", "/examples/server-pdf/loading"):
            self.assertIn('<link rel="canonical" href="http://testserver', self.html(path), path)

    def test_no_page_text_names_php_laravel_fastapi_or_artisan(self) -> None:
        for slug in SLUGS:
            html = re.sub(r"<pre[\s\S]*?</pre>", "", self.html(f"/examples/{slug}"))
            html = re.sub(r"languages/php|php\.min\.js", "", html)
            self.assertNotRegex(html, r"\bPHP\b|Laravel|artisan|FastAPI|Express\b|Node\.js backend", slug)

    def test_fill_and_edit_together_add_their_record_and_form_to_the_page_config(self) -> None:
        self.assertEqual(page_config(self.html("/examples/edit-together?form=contact-team"))["formId"], "contact-team")
        self.assertEqual(page_config(self.html("/examples/edit-together"))["formId"], "support-team")
        self.assertEqual(page_config(self.html("/examples/fill-together?record=new"))["record"], "new")

    def test_the_stylesheets_come_in_the_meta_prompts_order(self) -> None:
        def names(path: str) -> list[str]:
            return [re.sub(r"^https://unpkg\.com/(@?[^@]+)@[^/]+/", r"\1/", href) for href in stylesheets(self.html(path))]
        head = ["/shared/ui/fonts.css", "/static/css/site.css"]
        highlight = "@highlightjs/cdn-assets/styles/github-dark.min.css"
        self.assertEqual(names("/examples/save-response"), [*head, "survey-core/survey-core.min.css", "survey-core/collaboration.min.css",
                                                            "survey-core/themes/adapters/tailwind4.min.css", "/shared/ui/survey-overrides.css", highlight])
        self.assertEqual(names("/examples/creator-load-save"), [*head, "survey-core/survey-core.min.css",
                                                                "survey-creator-core/survey-creator-core.min.css",
                                                                "survey-creator-core/collaboration.min.css",
                                                                "survey-core/themes/adapters/tailwind4.min.css", highlight])
        self.assertEqual(names("/examples/dashboard"), [*head, "survey-core/survey-core.min.css", "survey-analytics/survey.analytics.min.css",
                                                        "survey-core/themes/adapters/tailwind4.min.css", highlight])
        self.assertIn(".sd-theme-root { --sjs2-typography-font-family-text: var(--font-sans); }", self.html("/examples/dashboard"))
        self.assertEqual(names("/examples/creator-load-save?form")[2], "survey-core/survey-core.min.css")
        self.assertEqual(self.html("/").count('rel="preload" as="font"'), 4)

    @override_settings(SURVEYJS_BUILD="main@abc1234")
    def test_the_build_line_shows_when_surveyjs_build_is_set(self) -> None:
        self.assertIn("Running main@abc1234", self.html("/"))
        self.assertIn("Running main@abc1234", self.html("/examples/dashboard"))

    def test_relay_urls_win_when_set(self) -> None:
        with override_settings(RELAY_URL="wss://relay.example.com", EDIT_RELAY_URL="wss://edit.example.com"):
            relay = page_config(self.html("/examples/edit-together"))["relay"]
        self.assertEqual((relay["fill"]["url"], relay["edit"]["url"]), ("wss://relay.example.com", "wss://edit.example.com"))

    def test_health_answers_without_the_database(self) -> None:
        with self.assertNumQueries(0):
            r = self.api.get("/up", user=None)
        self.assertEqual((r.status_code, r.json()), (200, {"status": "ok"}))


class SharedFilesTests(TransactionTestCase):
    """Through config.asgi.application, as uvicorn serves it, with DEBUG off and on (WhiteNoise's autorefresh)."""

    def check(self) -> None:
        async def run() -> list:
            async with asgi_client() as client:
                served = [(path, (await client.get(path))) for path in (
                    "/shared/ui/page-tabs.js", "/shared/client/host.js", "/shared/samples/support-help.svg",
                    "/shared/ui/fonts/lato/LatoLatin-Bold.woff2", "/shared/definitions/dashboard.json", "/shared/ui/theme.css",
                    "/static/css/site.css")]
                refused = [(path, (await client.get(path)).status_code) for path in (
                    "/shared/seed/forms.json", "/shared/contract-tests/run.mjs", "/shared/CONTRACT", "/shared/ui/",
                    "/shared/%2e%2e/pyproject.toml", "/shared/..%2fpyproject.toml")]
                return [served, refused]
        served, refused = async_to_sync(run)()
        types = {".js": "text/javascript", ".svg": "image/svg+xml", ".woff2": "font/woff2", ".json": "application/json", ".css": "text/css"}
        for path, response in served:
            self.assertEqual((response.status_code, response.headers["content-type"].split(";")[0]),
                             (200, types[Path(path).suffix]), path)
        for path, status in refused:
            self.assertEqual(status, 404, path)
        self.assertEqual(self.raw_status_codes(), [404, 404, 404])

    def raw_status_codes(self) -> list[int]:
        """Paths with .. sent as written (an HTTP client would resolve them first)."""
        from config.asgi import application

        async def run() -> list[int]:
            codes = []
            for path in ("/shared/../pyproject.toml", "/shared/client/../../pyproject.toml", "/shared/ui/../../.env"):
                status: list[int] = []

                async def send(message: dict) -> None:
                    if message["type"] == "http.response.start":
                        status.append(message["status"])

                pending = [{"type": "http.request", "body": b""}]

                async def receive() -> dict:   # the body once, then nothing until Django is done
                    if pending:
                        return pending.pop()
                    await asyncio.Event().wait()
                    return {"type": "http.disconnect"}
                scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                         "path": path, "raw_path": path.encode(), "root_path": "", "query_string": b"",
                         "headers": [(b"host", b"testserver")], "server": ("testserver", 80), "client": ("127.0.0.1", 1)}
                await application(scope, receive, send)
                codes.append(status[0])
            return codes
        return async_to_sync(run)()

    def test_debug_off(self) -> None:
        self.check()

    def test_debug_on(self) -> None:
        with override_settings(DEBUG=True):
            self.check()


class ProxyTests(TransactionTestCase):
    def test_x_forwarded_proto_https_gives_https_urls_and_wss_relays(self) -> None:
        from config.asgi import application

        async def run() -> list[str]:
            proxied = ProxyHeadersMiddleware(application, trusted_hosts="*")   # what uvicorn runs with proxy_headers=True
            async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=proxied), base_url="http://demo.example.com") as client:
                headers = {"X-Forwarded-Proto": "https", "Cookie": "demo_user=alice"}
                return [(await client.get("/examples/fill-together", headers=headers)).text,
                        (await client.get("/", headers=headers)).text,
                        (await client.get("/examples/edit-together", headers={"Cookie": "demo_user=alice"})).text]
        page, catalog, plain = async_to_sync(run)()
        self.assertIn('<link rel="canonical" href="https://demo.example.com/examples/fill-together">', page)
        self.assertEqual(page_config(page)["relay"]["fill"]["url"], "wss://demo.example.com")
        self.assertIn('"fill": {"url": "wss://demo.example.com"', page)
        self.assertIn('<link rel="canonical" href="https://demo.example.com/">', catalog)
        self.assertEqual(page_config(plain)["relay"]["edit"]["url"], "ws://demo.example.com")
