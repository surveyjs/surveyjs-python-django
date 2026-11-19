"""python manage.py serve [--reload]: start the app, pages, API and relays on one port, with uvicorn.

It checks the port before anything else, migrates (creating and seeding the database when needed), prints which
checkout is serving, then runs uvicorn on config.asgi:application with the proxy headers and the ASGI lifespan
on. `python manage.py runserver` serves the pages and the API too, but as WSGI only: the relays need ASGI.
"""

import os
import socket
import subprocess
import sys

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

BUSY = ("Port {port} is already in use. Another copy of this app (another checkout or branch?) may be running. "
        "Stop it, or set APP_PORT.")


def port_answers(port: int) -> bool:
    """Is something already answering on the port? Don't rely on the bind error: on Windows it comes late, and a
    server on 0.0.0.0 and another on 127.0.0.1 can both bind."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def git_build() -> str | None:
    """`<branch>@<short commit>` of this checkout, or None without git (or before the first commit)."""
    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=2,
                              check=True).stdout.strip()
    try:
        return f"{git('rev-parse', '--abbrev-ref', 'HEAD')}@{git('rev-parse', '--short', 'HEAD')}"
    except (OSError, subprocess.SubprocessError):
        return None


class Command(BaseCommand):
    help = "Start the app with uvicorn on APP_HOST:APP_PORT, after checking the port and migrating."
    requires_system_checks = []   # the port check comes first; `migrate` runs the checks

    def add_arguments(self, parser):
        parser.add_argument("--reload", action="store_true", help="Restart when a Python file changes.")

    def handle(self, *args, **options):
        port = settings.APP_PORT
        if port_answers(port):
            self.stderr.write(BUSY.format(port=port), ending="\n")
            sys.exit(1)

        call_command("migrate", interactive=False, verbosity=0)   # creates and seeds the database when needed

        build = settings.SURVEYJS_BUILD or git_build()
        if build:
            settings.SURVEYJS_BUILD = build        # this process's pages
            os.environ["SURVEYJS_BUILD"] = build   # --reload's worker reads the settings again
        self.stdout.write(f"Serving {settings.BASE_DIR}{f' ({build})' if build else ''} on http://127.0.0.1:{port}")
        self.stdout.flush()

        import uvicorn
        from uvicorn.config import LOGGING_CONFIG

        # uvicorn's log format for Django's and the app's loggers too, to stderr
        loggers = {name: {"handlers": ["default"], "level": "INFO", "propagate": False} for name in ("django", "examples", "demo")}
        uvicorn.run(
            "config.asgi:application",
            host=settings.APP_HOST,
            port=port,
            reload=options["reload"],
            lifespan="on",                                       # config/lifespan.py: the pruner, closing the HTTP client
            proxy_headers=True,                                  # X-Forwarded-Proto and -For, from these addresses:
            forwarded_allow_ips=settings.FORWARDED_ALLOW_IPS,
            log_config={**LOGGING_CONFIG, "loggers": {**LOGGING_CONFIG["loggers"], **loggers}},
        )
