"""Settings precedence: the environment wins over .env, and .env over settings.env. The real config/settings.py runs
in a subprocess from a scratch copy of the project folder, with its own two files."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

PRINT = ("import json, config.settings as s; print(json.dumps({'AI_MODEL': s.AI_MODEL, 'AI_BASE_URL': s.AI_BASE_URL, "
         "'APP_PORT': s.APP_PORT, 'DEMO_MODE': s.DEMO_MODE, 'AI_API_KEY': s.AI_API_KEY, 'DEBUG': s.DEBUG}))")


class SettingsTests(SimpleTestCase):
    def read(self, environment: dict[str, str]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir()
            shutil.copy(settings.BASE_DIR / "config" / "settings.py", root / "config" / "settings.py")
            (root / "config" / "__init__.py").write_text("", encoding="utf-8")
            (root / "settings.env").write_text("AI_MODEL=from-settings-env\nAI_BASE_URL=https://settings.example/v1/\n"
                                               "APP_PORT=8100\nDEMO_MODE=yes\nDJANGO_DEBUG=true\n", encoding="utf-8")
            (root / ".env").write_text("AI_MODEL=from-dotenv\nAI_API_KEY=secret\n", encoding="utf-8")
            env = {key: value for key, value in os.environ.items()
                   if key not in ("AI_MODEL", "AI_BASE_URL", "APP_PORT", "DEMO_MODE", "AI_API_KEY", "DJANGO_DEBUG", "DATA_DIR")}
            result = subprocess.run([sys.executable, "-W", "error", "-c", PRINT], cwd=root, env={**env, "PYTHONPATH": tmp, **environment},
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_environment_then_dotenv_then_settings_env(self) -> None:
        self.assertEqual(self.read({}), {"AI_MODEL": "from-dotenv", "AI_BASE_URL": "https://settings.example/v1",
                                         "APP_PORT": 8100, "DEMO_MODE": True, "AI_API_KEY": "secret", "DEBUG": True})
        self.assertEqual(self.read({"AI_MODEL": "from-environment", "APP_PORT": "8200", "DEMO_MODE": "off"}),
                         {"AI_MODEL": "from-environment", "AI_BASE_URL": "https://settings.example/v1", "APP_PORT": 8200,
                          "DEMO_MODE": False, "AI_API_KEY": "secret", "DEBUG": True})

    def test_a_blank_variable_overrides_dotenv_with_nothing(self) -> None:
        self.assertIsNone(self.read({"AI_API_KEY": " "})["AI_API_KEY"])

    def test_switches_accept_1_true_on_yes(self) -> None:
        for value, expected in (("1", True), ("true", True), ("on", True), ("yes", True), ("false", False), ("0", False)):
            self.assertIs(self.read({"DEMO_MODE": value})["DEMO_MODE"], expected, value)
