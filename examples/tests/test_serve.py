"""manage.py serve refuses a port that something answers on, with the meta prompt's message, before migrate runs or
anything is written to the data folder; and the Python version check comes first."""

import os
import socket
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class ServeTests(SimpleTestCase):
    def test_serve_refuses_a_busy_port_before_any_startup_work(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            data_dir = os.path.join(tmp, "data")
            for debug in ("true", "false"):   # production mode too: its secret key file comes later
                env = {**os.environ, "APP_PORT": str(port), "DATA_DIR": data_dir, "SURVEYJS_BUILD": "test@0000000",
                       "DJANGO_DEBUG": debug, "DJANGO_SETTINGS_MODULE": "config.settings"}
                result = subprocess.run([sys.executable, "-W", "error", "manage.py", "serve"], cwd=settings.BASE_DIR, env=env,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(result.stderr.strip(), f"Port {port} is already in use. Another copy of this app (another checkout "
                                                        "or branch?) may be running. Stop it, or set APP_PORT.")
                self.assertEqual(os.listdir(data_dir), [], "nothing was created, migrated or seeded")

    def test_the_version_check_comes_first(self) -> None:
        source = (settings.BASE_DIR / "manage.py").read_text(encoding="utf-8")
        self.assertLess(source.index("sys.version_info < (3, 14)"), source.index("django"))
        self.assertIn("Python 3.14 or newer is required (this is", source)

    def test_ready_does_no_database_or_file_work(self) -> None:
        source = (settings.BASE_DIR / "examples" / "apps.py").read_text(encoding="utf-8")
        ready = source[source.index("def ready"):]
        self.assertNotRegex(ready, r"objects|cursor|open\(|write|mkdir|migrate\(")
