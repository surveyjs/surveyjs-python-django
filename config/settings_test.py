"""The settings `python manage.py test` runs with (manage.py picks this module for `test`).

A temporary DATA_DIR, and every private key and switch empty or off, so neither settings.env, .env nor the
shell changes a test result. Tests turn things on with override_settings.
"""

import atexit
import os
import shutil
import tempfile

# Before config.settings reads it: the environment wins over .env and settings.env
_DATA_DIR = tempfile.mkdtemp(prefix='surveyjs-tests-')
os.environ['DATA_DIR'] = _DATA_DIR
atexit.register(shutil.rmtree, _DATA_DIR, ignore_errors=True)

from config.settings import *  # noqa: E402,F403
from config.settings import DATABASES, LOGGING  # noqa: E402

# The test database is a file next to the others, as in production (WAL, IMMEDIATE), not SQLite in memory
DATABASES['default']['TEST'] = {'NAME': DATA_DIR / 'test.sqlite'}  # noqa: F405

DEBUG = False
APP_PORT = 8000
SECRET_KEY = 'django-insecure-tests'
ALLOWED_HOSTS = ['testserver', 'demo.example.com', 'localhost', '127.0.0.1']

# Nothing listens on the discard port: the SurveyJS service "isn't running" unless a test mocks it
SURVEYJS_SERVICE_URL = 'http://127.0.0.1:9'
VALIDATE_RESPONSES = False
LINT_DEFINITIONS = False
DEMO_MODE = False
RELAY_URL = None
EDIT_RELAY_URL = None
SURVEYJS_LICENSE_KEY = None
AI_BASE_URL = 'http://127.0.0.1:9/v1'
AI_API_KEY = None
AI_MODEL = 'stub'
SURVEYJS_AI_PROVIDER = None
SURVEYJS_AI_MODEL = None
SURVEYJS_OLLAMA_BASE_URL = None
OPENAI_API_KEY = None
ANTHROPIC_API_KEY = None
SURVEYJS_BUILD = None
SURVEYJS_DOCS = 'https://surveyjs.io/documentation/backend-integration-django'
SURVEYJS_GITHUB = 'https://github.com/surveyjs/surveyjs-python-django'

# Tests that expect an error log read it with assertLogs; keep the rest of the run's output quiet
LOGGING['handlers']['console']['level'] = 'CRITICAL'
