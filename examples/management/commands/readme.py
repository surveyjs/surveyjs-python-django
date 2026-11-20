"""python manage.py readme: regenerates the README's example table (between the steps markers) from
surveyjs-integration.json."""

import json
import re
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

DOCS = "https://surveyjs.io/documentation/backend-integration-python-django"


class Command(BaseCommand):
    help = "Regenerate the README's example table from surveyjs-integration.json."
    requires_system_checks = []

    def handle(self, *args, **options):
        manifest = json.loads((settings.BASE_DIR / "surveyjs-integration.json").read_text(encoding="utf-8"))
        readme_path = settings.BASE_DIR / "README.md"
        readme = readme_path.read_text(encoding="utf-8")

        def file(step: dict, role: str) -> str:
            path = step["files"].get(role)
            return f"[`{path}`]({path})" if path else "—"

        def run(step: dict) -> str:
            return f"[{step['page']}]({manifest['live']}{step['page']})" if manifest.get("live") else f"`{step['page']}`"

        rows = ["| Example | Run | Server | Client | Page | Licence |", "|---|---|---|---|---|---|"]
        rows += [f"| [{step['title']}]({DOCS}#{step['anchor']}) | {run(step)} | {file(step, 'server')} | {file(step, 'client')} "
                 f"| {file(step, 'page')} | {step['licence']} |" for step in manifest["steps"]]

        marker = re.compile(r"(<!-- steps:start[^>]*-->)[\s\S]*?(<!-- steps:end -->)")
        if not marker.search(readme):
            self.stderr.write("README.md needs <!-- steps:start --> and <!-- steps:end --> markers.")
            sys.exit(1)
        readme_path.write_text(marker.sub(lambda m: f"{m.group(1)}\n" + "\n".join(rows) + f"\n{m.group(2)}", readme),
                               encoding="utf-8", newline="\n")
        self.stdout.write(f"Updated the example table in README.md ({len(manifest['steps'])} examples).")
