"""Demo only: the catalog and the example pages around the examples. The integration code is in
examples/views/<snake_slug>.py; these views only show it running.

The reference's Blade views compute a few things in @php blocks (the records to pick from, the edit-together form
check and its 400, server-pdf's claims, ?form, ?version). Here PAGE_DATA does that work before the template
renders: templates neither query nor set a status, and a Django template can't ask whether a block is filled, so
render_example() also says which stylesheets the page loads (`theme`) and whether it has an `about` text.
"""

import json
import re
from collections.abc import Callable
from itertools import groupby
from typing import Any

from django.conf import settings
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.template.loader import render_to_string

from demo import users
from demo.code_panel import code_definitions, code_panel
from demo.manifest import docs_url, find_step, read_manifest
from examples.auth import can
from examples.db import JsonExtract
from examples.frontend import FONTS, HIGHLIGHT_THEME, stylesheets
from examples.models import Form, Response

TITLE = "Python Backend Integration with Django"
"""The catalog's browser title, and the example pages' header next to the SurveyJS pill"""
HEADER = "Step-by-Step Python Backend Integration with Django"
"""The catalog header, next to the logo"""

SECTIONS = [
    ("Run Forms", "preview", "SurveyJS Form Library displays forms in the browser. Start with a Python endpoint that "
     "saves submitted answers, then add the workflows your application needs."),
    ("Analyze Results with Dashboard", "graph", "SurveyJS Dashboard lets users analyze responses with interactive "
     "charts in the browser. Your Python backend supplies the saved responses."),
    ("Edit Forms in Survey Creator", "embed-creator", "Survey Creator lets users build and edit forms in the browser. "
     "Your Python backend loads and saves form JSON schemas and checks that users have permission to make changes."),
    ("Run Server-Side Workflows", "server", "Use a Node.js service alongside your Python application to run SurveyJS "
     "workflows: validate responses, check form schemas, generate PDFs, and extract answers from documents."),
]
"""The catalog's sections: title, the hero card's icon (shared/ui/images/icon-*.svg) and the intro."""

STACK_LOGOS = ["nextjs", "nodejs", "aspnet", "php", "wordpress", "model", "postgresql", "mongodb", "python"]
"""The footer's logos, by file (shared/ui/images/stack-*.svg)"""

PANEL_TABS = [("description", "Description"), ("requests", "Requests"), ("stored", "Data")]
MAIN_TABS = [("demo", "Demo"), ("code", "Code")]
CREATOR_PAGES = {"creator-load-save", "creator-uploads", "ai-translation", "variable-presets", "edit-together",
                 "lint-definition"}


def _site(request: HttpRequest) -> dict[str, Any]:
    """What the catalog, the PDF loading page and the example pages all read."""
    return {
        "title": TITLE,
        "header": HEADER,
        "build": settings.SURVEYJS_BUILD,
        "docs": docs_url(settings.SURVEYJS_DOCS),
        "github": settings.SURVEYJS_GITHUB,
        "canonical": request.build_absolute_uri(request.path),   # https behind a TLS proxy (X-Forwarded-Proto)
        "fonts": FONTS,
    }


def _anchor(text: str) -> str:
    """A catalog section's anchor: "Run Forms" -> "run-forms"."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def catalog(request: HttpRequest) -> HttpResponse:
    manifest = read_manifest()
    groups = {section: list(steps) for section, steps in groupby(manifest["steps"], key=lambda step: step["section"])}
    blob = f"{settings.SURVEYJS_GITHUB}/blob/{manifest['branch']}"
    sections = [{
        "title": title, "anchor": _anchor(title), "icon": icon, "intro": intro,
        "cards": [{
            "step": step,
            "licence": "MIT" if step["licence"].startswith("MIT") else "Commercial",
            "needs_ai": "needs an AI provider" in step["licence"],
            "source": f"{blob}/{step['files'].get('server') or step['files']['client']}",
            "guide": docs_url(settings.SURVEYJS_DOCS, step),
        } for step in groups[title]],
    } for title, icon, intro in SECTIONS if groups.get(title)]
    return render(request, "catalog.html", {**_site(request), "sections": sections, "stack_logos": STACK_LOGOS * 2})


def pdf_loading(request: HttpRequest) -> HttpResponse:
    return render(request, "examples/pdf-loading.html", _site(request))


def example(request: HttpRequest, slug: str) -> HttpResponse:
    if not re.fullmatch(r"[a-z0-9-]+", slug) or find_step(slug) is None:
        raise Http404("Unknown example")
    return render_example(request, slug)


def render_example(request: HttpRequest, slug: str, **context: Any) -> HttpResponse:
    """An example page: signs in the page's demo user, adds the page config, runs PAGE_DATA, renders the template.
    /claim (Option A of load-definition-variables-data) calls it with the definition and the variables."""
    step = find_step(slug)
    if step is None:
        raise Http404("Unknown example")
    response = HttpResponse()
    users.sign_in_for_page(slug, request, response)   # sets request.user, and the demo_user cookie if it changes
    user = request.user
    try:
        page_data = PAGE_DATA.get(slug, lambda *_: {})(request, user)
    except InvalidFormId:
        return HttpResponse("Invalid form ID", status=400, content_type="text/plain; charset=utf-8")
    page = page_config(request, step, user)
    page.update(page_data.pop("page", {}))
    form_mode = page_data.get("form_mode", False)
    theme = "dashboard" if slug == "dashboard" else "creator" if slug in CREATOR_PAGES and not form_mode else "survey"
    offered = users.for_page(slug)
    response.content = render_to_string(f"examples/{slug}.html", {
        **_site(request),
        "step": step,
        "page": page,
        "theme": theme,
        "styles": stylesheets()[theme],
        "highlight_theme": HIGHLIGHT_THEME,
        "panel_tabs": PANEL_TABS,
        "main_tabs": MAIN_TABS,
        "user_options": [(key, users.LABELS[key], key == page["demoUser"]) for key in offered] if len(offered) > 1 else [],
        "show_actions": len(offered) > 1 or slug != "dashboard",   # every page but the dashboard fills `actions`
        "has_about": slug == "extract-from-paper" or (slug in ("fill-together", "edit-together") and settings.DEMO_MODE),
        "commercial": step["licence"].startswith("Commercial"),
        "needs_ai": "needs an AI provider" in step["licence"],
        "step_docs": docs_url(settings.SURVEYJS_DOCS, step),
        "join_failed": getattr(request, "scope", {}).get("demo_join_failed", False),
        "code_definitions": code_definitions(settings.SURVEYJS_GITHUB, step),
        "code_panel": code_panel(settings.SURVEYJS_GITHUB, step),
        "switches": {"validate_responses": settings.VALIDATE_RESPONSES, "lint_definitions": settings.LINT_DEFINITIONS},
        "translation_configured": bool(settings.AI_API_KEY),
        "extraction_configured": bool(settings.SURVEYJS_AI_PROVIDER or settings.OPENAI_API_KEY or settings.ANTHROPIC_API_KEY),
        "option_a": "form_definition" in context,
        **page_data,
        **context,
    }, request)
    return response


def _read_json(path: str) -> Any:
    return json.loads((settings.BASE_DIR / path).read_text(encoding="utf-8"))


def page_config(request: HttpRequest, step: dict[str, Any], user: Any) -> dict[str, Any]:
    """window.SURVEYJS_PAGE: what shared/client/host.js and the example modules read."""
    definitions = {role: _read_json(path) for role, path in step["files"].items() if role.startswith("definition")}
    if step["slug"] == "extract-from-paper":
        form = Form.objects.filter(key="work-order").first()
        if form is None:
            raise Http404("Unknown work order form")
        definitions["definition"] = json.loads(form.json)
    # The relays run in this app: the page's own origin, ws or wss as the visitor sees it (X-Forwarded-Proto)
    origin = f"{'wss' if request.is_secure() else 'ws'}://{request.get_host()}"
    signed_in = user.is_authenticated
    return {
        "slug": step["slug"],
        "version": read_manifest()["surveyjsVersion"],
        "licenseKey": settings.SURVEYJS_LICENSE_KEY,
        "demoUser": user.username if signed_in else "none",
        "user": {"key": user.username, "name": user.get_full_name(), "plan": user.plan,
                 "isEditor": can(user, "edit-forms")} if signed_in else None,
        "relay": {
            "fill": {"url": settings.RELAY_URL or origin, "port": settings.APP_PORT},
            "edit": {"url": settings.EDIT_RELAY_URL or origin, "port": settings.APP_PORT},
        },
        "demoMode": settings.DEMO_MODE,
        "sandboxId": getattr(request, "scope", {}).get("demo_sid"),
        "switches": {"validateResponses": settings.VALIDATE_RESPONSES, "lintDefinitions": settings.LINT_DEFINITIONS},
        **definitions,
    }


# What some example pages compute before they render: the reference does this in the views' @php blocks.

def _records(form_id: str, label_key: str, customer_email: str | None = None) -> list[dict[str, str]]:
    rows = Response.objects.filter(form_id=form_id)
    if customer_email is not None:
        rows = rows.annotate(email=JsonExtract("data", "$.customer_email")).filter(email=customer_email)
    return [{"id": str(row.id), "label": f"#{row.id} · {_label(json.loads(row.data), label_key)}"}
            for row in rows.order_by("id")[:10]]


def _label(data: Any, key: str) -> str:
    value = data.get(key) if isinstance(data, dict) else None
    return "" if value is None else str(value)


def _load_definition(request: HttpRequest, user: Any) -> dict[str, Any]:
    return {"record": request.GET.get("record", ""),
            "records": _records("claim", "customer_email", user.email if user.is_authenticated else "")}


def _fill_together(request: HttpRequest, user: Any) -> dict[str, Any]:
    records = _records("job-sheet", "customer")
    record = request.GET.get("record", records[0]["id"] if records else "new")
    return {"records": records, "record": record, "known": any(r["id"] == record for r in records),
            "page": {"record": record}}


def _edit_together(request: HttpRequest, user: Any) -> dict[str, Any]:
    form_id = request.GET.get("form", "support-team")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", form_id):
        raise InvalidFormId
    forms = []
    for form in Form.objects.filter(Q(key__endswith="-team") | Q(key__startswith="team-")).order_by("key"):
        title = json.loads(form.json).get("title")
        label = title if isinstance(title, str) else title.get("default") if isinstance(title, dict) else None
        forms.append({"id": form.key, "label": label or "Untitled form"})
    return {"forms": forms, "form_id": form_id, "known": any(f["id"] == form_id for f in forms), "page": {"formId": form_id}}


def _server_pdf(request: HttpRequest, user: Any) -> dict[str, Any]:
    claims = []
    for row in Response.objects.filter(form_id="claim").order_by("-id")[:10]:
        answers = json.loads(row.data)
        email = answers.get("customer_email") if isinstance(answers, dict) else None
        label = email if isinstance(email, (str, int, float)) else "No email provided"
        claims.append({"id": row.id, "label": label, "json": json.dumps(answers, indent=4, ensure_ascii=False)})
    return {"claims": claims}


PAGE_DATA: dict[str, Callable[[HttpRequest, Any], dict[str, Any]]] = {
    "load-definition-variables-data": _load_definition,
    "fill-together": _fill_together,
    "edit-together": _edit_together,
    "relational-storage": lambda request, user: {
        "version": "v2" if request.GET.get("version") == "v2" else "v1",
        "versions": [("v1", "v1: Original form"), ("v2", "v2: Redesigned form")],
    },
    "server-pdf": _server_pdf,
    "creator-load-save": lambda request, user: {"form_mode": "form" in request.GET},
    "creator-uploads": lambda request, user: {"form_mode": "form" in request.GET},
}
"""The page's own context; a "page" entry is merged into window.SURVEYJS_PAGE."""


class InvalidFormId(Exception):
    """edit-together's ?form isn't a form id: the page answers 400."""


def not_found(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "404.html", status=404)


def server_error(request: HttpRequest) -> HttpResponse:
    return render(request, "500.html", status=500)
