"""python manage.py contract [--steps save-response,choices-from-web] [--smoke]

Runs the shared contract test (shared/contract-tests/run.mjs), or with --smoke the smoke test (shared/smoke/run.mjs),
against a fresh DATA_DIR and this app on a free port, as in production (DJANGO_DEBUG=false), then stops the app and
exits with the test's code. Works on Windows and Linux; needs Node 22+ on PATH for the test itself.

Passed through from the environment: SERVICE (off or on; off points the app at a port nothing listens on), AI (off
or stub), VALIDATE_RESPONSES, LINT_DEFINITIONS, DEMO_MODE, SURVEYJS_SERVICE_URL and the AI_* settings. With
AI=stub, start the stub first (docker-compose.ci.yml) and set AI_BASE_URL=http://127.0.0.1:3020/v1 AI_API_KEY=stub
AI_MODEL=stub. The relays run in the app, so RELAY_URL and EDIT_RELAY_URL are its ws:// origin.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

# Off means off: the app's settings.env and .env must not switch translation or extraction on. A space overrides
# them with nothing (config/settings.py treats blank values as unset).
AI_SETTINGS = ["AI_API_KEY", "SURVEYJS_AI_PROVIDER", "SURVEYJS_AI_MODEL", "SURVEYJS_OLLAMA_BASE_URL", "OPENAI_API_KEY",
               "ANTHROPIC_API_KEY"]
SWITCHES = ["VALIDATE_RESPONSES", "LINT_DEFINITIONS", "DEMO_MODE"]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def wait_for(url: str, app: subprocess.Popen[bytes], seconds: float = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if app.poll() is not None:
            raise RuntimeError(f"The app stopped with exit code {app.returncode}")
        try:
            with urllib.request.urlopen(url, timeout=1) as answer:
                if answer.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"The app did not answer {url} within {seconds} s")


def stop(app: subprocess.Popen[bytes], port: int) -> None:
    """Stop the app and what it started. On Windows a venv's python.exe is a launcher that runs the real interpreter
    as its child, so terminating the launcher alone would leave uvicorn serving: end the whole process tree, then
    wait until nothing answers on the port."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(app.pid)], capture_output=True)
    else:
        app.terminate()
    try:
        app.wait(timeout=10)
    except subprocess.TimeoutExpired:
        app.kill()
        app.wait()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            time.sleep(0.2)
        except OSError:
            return


def remove(log: Path, data_dir: Path) -> None:
    """The run's log and DATA_DIR. On Windows a process that just ended may hold its files a moment longer."""
    for _ in range(25):
        try:
            log.unlink(missing_ok=True)
            break
        except PermissionError:
            time.sleep(0.2)
    shutil.rmtree(data_dir, ignore_errors=True)


class Command(BaseCommand):
    help = "Run the shared contract test (or --smoke) against this app on a free port and a fresh DATA_DIR."
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--steps", help="Only these examples' checks: slugs, comma-separated.")
        parser.add_argument("--smoke", action="store_true", help="Run shared/smoke/run.mjs instead.")

    def handle(self, *args, **options):
        sys.exit(self.run(options["steps"], options["smoke"]))

    def run(self, steps: str | None, smoke: bool) -> int:
        node = shutil.which("node")
        if node is None:
            self.stderr.write("Node.js 22 or newer is needed on PATH to run the contract test (shared/contract-tests/run.mjs).")
            return 1
        root = settings.BASE_DIR
        data_dir = Path(tempfile.mkdtemp(prefix="surveyjs-contract-"))
        port = free_port()
        origin = f"http://127.0.0.1:{port}"
        env = {**os.environ, "DATA_DIR": str(data_dir), "APP_PORT": str(port), "APP_HOST": "127.0.0.1",
               "DJANGO_DEBUG": "false", "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
               "DJANGO_SETTINGS_MODULE": "config.settings",
               "SERVICE": os.environ.get("SERVICE", "off"), "AI": os.environ.get("AI", "off"),
               "SURVEYJS_BUILD": os.environ.get("SURVEYJS_BUILD", "contract"), "PYTHONUNBUFFERED": "1"}
        for switch in SWITCHES:   # what the test expects is what the app runs with, whatever settings.env and .env say
            env[switch] = os.environ.get(switch) or "false"
        if env["AI"] != "stub":
            env.update({name: " " for name in AI_SETTINGS})
        if env["SERVICE"] == "off":   # off means not running, also when a service answers on 3010: a port nothing listens on
            env["SURVEYJS_SERVICE_URL"] = f"http://127.0.0.1:{free_port()}"

        log = (data_dir.parent / f"{data_dir.name}.log").open("w+b")
        code = 1
        app = None
        try:
            subprocess.run([sys.executable, "manage.py", "migrate", "--noinput", "-v", "0"], cwd=root, env=env, check=True,
                           stdout=log, stderr=subprocess.STDOUT)
            app = subprocess.Popen([sys.executable, "-m", "uvicorn", "config.asgi:application", "--host", "127.0.0.1",
                                    "--port", str(port), "--lifespan", "on"], cwd=root, env=env, stdout=log,
                                   stderr=subprocess.STDOUT)
            wait_for(f"{origin}/up", app)
            self.stdout.write(f"Started the app on port {port} (DATA_DIR {data_dir})")
            self.stdout.flush()
            test = "shared/smoke/run.mjs" if smoke else "shared/contract-tests/run.mjs"
            code = subprocess.call([node, test, *([f"--steps={steps}"] if steps else [])], cwd=root,
                                   env={**env, "BASE_URL": origin, "RELAY_URL": f"ws://127.0.0.1:{port}",
                                        "EDIT_RELAY_URL": f"ws://127.0.0.1:{port}"})
        except (RuntimeError, subprocess.CalledProcessError) as error:
            self.stderr.write(str(error))
        finally:
            if app is not None:
                stop(app, port)
            log.seek(0)
            output = log.read().decode("utf-8", "replace")
            log.close()
            if code != 0 and output:
                self.stdout.write(f"--- the app's output\n{output[-6000:]}")
            remove(Path(log.name), data_dir)
        return code
