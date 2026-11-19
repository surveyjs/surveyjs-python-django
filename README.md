# SurveyJS + Python: the backend integration examples on Django

This is the Python code behind [Integrate SurveyJS with Django](https://surveyjs.io/documentation/backend-integration-django), as a Django project you can run example by example. Each example of that page has a page here that runs the real SurveyJS component against these views, with a short "Try this" list, a live request log, a "What the server stored" panel and the code that just ran. SurveyJS has no backend of its own, so treat these as starting points for your own app.

- SurveyJS demos: [app.demos.surveyjs.io](https://app.demos.surveyjs.io)
- The same examples for other platforms: [Python (FastAPI)](https://github.com/surveyjs/surveyjs-python-fastapi), [PHP (Laravel)](https://github.com/surveyjs/surveyjs-php-laravel), [ASP.NET Core](https://github.com/surveyjs/surveyjs-aspnet-core), [Node.js (Express)](https://github.com/surveyjs/surveyjs-nodejs), [Next.js](https://github.com/surveyjs/surveyjs-nextjs), [Java (Spring Boot)](https://github.com/surveyjs/surveyjs-java-spring-boot)

There is no hosted catalog for this repository yet.

## Run it

You need Python 3.14 or later. Docker runs the SurveyJS service for the four Run Server-Side Workflows examples, and Node.js 22 or later is only for the browser tests and the CSS build (see [Prerequisites](#prerequisites)).

```powershell
git clone https://github.com/surveyjs/surveyjs-python-django.git
cd surveyjs-python-django
py -3.15 -m venv .venv                 # or: python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py serve                 # http://127.0.0.1:8000
```

```bash
git clone https://github.com/surveyjs/surveyjs-python-django.git
cd surveyjs-python-django
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py serve                 # http://127.0.0.1:8000
```

`python manage.py serve` runs `migrate` first, which creates `storage/database.sqlite` and seeds it on the first start, then serves the app with uvicorn: the pages, the API and the two WebSocket relays on one port. While you work on the code, run `python manage.py serve --reload`.

- **`runserver` works too, without the relays.** `python manage.py migrate` then `python manage.py runserver` serves every page and endpoint, but Django's `runserver` is WSGI only unless Daphne is installed, so Fill Forms Together and Edit Forms Together show "Disconnected"; it also skips the port check and the build line. There is no Daphne here: it doesn't install on Python 3.15 for Windows (see [Prerequisites](#prerequisites)).
- **Fill Forms Together** and **Edit Forms Together** use WebSocket relays that run inside the app, on its port (`/ws/rooms/<id>` and `/ws/forms/<id>`), as Channels consumers. There is nothing else to start.
- **Run Server-Side Workflows** (validate, lint, PDF, extract) call the SurveyJS service, [SurveyJS Server](https://github.com/surveyjs/surveyjs-server). Start it with `docker compose up -d surveyjs` (it listens on `http://localhost:3010`), set `VALIDATE_RESPONSES=true` and `LINT_DEFINITIONS=true` in `settings.env` to switch Validate Responses and Lint JSON Schemas on, then restart the app. Extract Responses from Documents also needs an AI provider for the service (`SURVEYJS_AI_PROVIDER` in `settings.env`, its key in `.env`, which you copy from `.env.example`).
- The tests:
  - `python -W error manage.py test`: Django's test runner, about ten seconds, no browser, no network, no service (it is mocked); a warning fails a test.
  - `python manage.py contract`: the shared contract test against a fresh database and this app on a free port (`SERVICE=on` with the service running; `--smoke` for the smoke test; `--steps save-response,dashboard` for some examples).
  - `npm ci`, `npx playwright install chromium` once, then `npm run test:browser`: the shared Playwright specs, and a check that every page loads without a console error.
  - `python manage.py surveyjs_check --complete`: the manifest, the regions, `shared/` and the pins.

`python manage.py serve` checks that nothing answers on the port first, then prints the folder it serves and its `<branch>@<commit>`:

```text
Serving C:\src\surveyjs-python-django (main@4a96b83) on http://127.0.0.1:8000
```

### Prerequisites

- **Python 3.14 or later** (3.15 recommended). `manage.py` stops at once on an older one: "Python 3.14 or newer is required (this is 3.13.5)". A missing package shows up as pip's own error at `pip install -r requirements.txt`.
- **Docker** for the SurveyJS service (`docker compose up -d surveyjs`). Without it, the four Run Server-Side Workflows examples answer `503` "SurveyJS service is not running at http://localhost:3010", and everything else works.
- **Node.js 22 or later**, only for the browser tests and the CSS build. `npm ci` on an older Node stops with npm's own `EBADENGINE` error (`engines` in `package.json`, `engine-strict` in `.npmrc`). Running the app never needs Node.

On Windows:

- Install Python 3.14 or 3.15 from [python.org](https://www.python.org/downloads/), with `py install 3.15` (the Python install manager), or with `winget install Python.Python.3.15`.
- `python` may be the Microsoft Store stub (`…\WindowsApps\python.exe`), which opens the Store instead of running. `py -3.15 -m venv .venv` avoids it; inside the activated venv, `python` is the venv's.
- If PowerShell refuses to run `Activate.ps1`, allow local scripts once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- After installing Python or Node, restart your editor, not only its terminal: VS Code's terminals inherit VS Code's environment. To refresh the current PowerShell terminal instead:

  ```powershell
  $env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  py --list
  ```

- Don't install `daphne` (or `channels[daphne]`) on Python 3.15 for Windows: it needs `autobahn`, and no autobahn release from 25.9 on has a wheel for it, so pip tries to build one with the Microsoft C++ Build Tools. Pinning `autobahn==24.4.2` is the only way. uvicorn serves the relays instead. For the same reason `requirements.txt` pins `uvicorn` without `[standard]`, so `--reload` uses uvicorn's own file watcher.
- Set a variable for one run like this, or put it in `settings.env`:

  ```powershell
  $env:APP_PORT=8001; python manage.py serve
  ```

  ```bash
  APP_PORT=8001 python manage.py serve
  ```

On Windows, a second server can bind a port another server listens on while the first keeps answering, and a bind error comes late. So `serve` connects to the port first, before it migrates or writes anything, and stops with "Port 8000 is already in use. Another copy of this app (another checkout or branch?) may be running. Stop it, or set APP_PORT."

### Stop everything

`Ctrl+C` in the terminal (with `--reload`, the reloader and its worker stop together), then `docker compose down` for the service. To find a server left running in another terminal or checkout:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object OwningProcess
Stop-Process -Id <OwningProcess>
```

```bash
lsof -i :8000
kill <PID>
```

On Windows a venv's `python.exe` is a launcher that starts the real interpreter as its child: stop the process that owns the port (the command above finds it), not only the launcher.

### Run a branch or a PR

- Check the branch out in its own folder, with `git worktree add ../surveyjs-python-django-pr <branch>` (for a pull request, `git fetch origin pull/<number>/head:pr-<number>` first) or a second clone. Each checkout has its own `.venv`, `.env` and `storage/`.
- Run one checkout on the default port at a time: stop the other one first, or start the second with `APP_PORT=8001` (PowerShell: `$env:APP_PORT=8001; python manage.py serve`).
- The SurveyJS service is shared: `docker-compose.yml` names its project `surveyjs-python-django`, so every checkout manages the same container. The FastAPI repository runs the same pinned service under its own project name; only one of the two can publish port 3010 at a time, and either serves both apps.
- The page says which checkout answered: "Running `<branch>@<commit>`" under the catalog's footer buttons and at the end of every example's Description panel.

## Docker

```bash
docker compose up --build    # http://127.0.0.1:8000, with the SurveyJS service next to it
```

The image (`Dockerfile`) is `python:3.15.2-slim` with `pip install -r requirements.txt` and `collectstatic`, runs as a non-root user, and starts with `python manage.py serve`, which migrates and seeds on start. Its environment sets `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS=*`, `APP_HOST=0.0.0.0`, `DATA_DIR=/app/storage` and `FORWARDED_ALLOW_IPS=*`; real environment variables win over `settings.env`, which the image includes. `.env` isn't copied into the image: `docker compose` passes the private keys in. Without `DJANGO_SECRET_KEY`, the app generates one into the volume the first time Django needs it. Its one volume, `/app/storage`, holds the database, the uploads, the visitor sandboxes, the relay snapshots and that key. Logs go to stderr (`docker compose logs app`). `GET /up` answers `200 {"status": "ok"}` without touching the database.

**One process, many visitors.** The image runs one uvicorn worker, on purpose: the relay rooms, the in-memory channel layer, Django's local-memory cache (the countries list) and the demo's AI counter live in the process's memory, and a second worker would split a room in two. Concurrency comes from async views: an extraction that waits up to 120 seconds for the service is an `await` on `httpx2.AsyncClient`, so other visitors are served meanwhile (see [Sync and async views](#sync-and-async-views)). To scale out to several processes or hosts, you need `channels_redis` for the channel layer, a shared store for the rooms, and a shared cache (Redis or the database cache); that is out of scope here.

On Windows, Docker Compose 5 can't build a service from a git URL (`failed to evaluate path "https://github.com/…"`), which the `surveyjs` service is: it hands the URL to the builder as a file path. Let Compose print the build and give it to the builder yourself, then start without building:

```powershell
docker compose build --print | docker buildx bake -f -
docker compose up -d --no-build
```

Linux and macOS (and CI) build with `docker compose up --build` as above.

### Behind a proxy

`serve` runs uvicorn with `proxy_headers=True`, trusting `X-Forwarded-For` and `X-Forwarded-Proto` from the addresses in `FORWARDED_ALLOW_IPS`: `127.0.0.1` by default, `*` in the image. uvicorn then sets the request's scheme itself, so `request.is_secure()` and `request.build_absolute_uri()` say `https` behind a TLS proxy without `SECURE_PROXY_SSL_HEADER`, and the relays' URLs are `wss://`. In your own production, set `DJANGO_ALLOWED_HOSTS` to your host names and `FORWARDED_ALLOW_IPS` to the proxy's addresses, and don't publish the app's port. The relays are on the app's own host and port, so the proxy needs no extra route, only WebSocket upgrades passed through on `/ws/`. For Traefik, next to your entry point and TLS labels:

```yaml
services:
  app:
    labels:
      - traefik.http.routers.surveyjs.rule=Host(`example.com`)
      - traefik.http.services.surveyjs.loadbalancer.server.port=8000
```

Traefik passes WebSocket upgrades on by default; nginx needs `proxy_set_header Upgrade $http_upgrade;` and `proxy_set_header Connection "upgrade";` on `/ws/`. `RELAY_URL` and `EDIT_RELAY_URL` are only needed when `/ws/` is served from another origin. The SurveyJS service stays internal (`expose: ["3000"]`): only the app calls it.

## Configuration

`config/settings.py` reads every setting once, with django-environ, from the environment and two files, and code reads `django.conf.settings`, never `os.environ`. `settings.env` is committed and holds every setting except the private keys. `.env` is git-ignored and holds only the private keys: `DJANGO_SECRET_KEY`, `SURVEYJS_LICENSE_KEY`, `AI_API_KEY`, `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` (copy `.env.example` to it). Variables set in the environment win, then `.env`, then `settings.env` (`Env.read_env()` keeps what is already set, so `.env` is read first). Switches accept `1`, `true`, `on` or `yes`. `python manage.py test` uses `config/settings_test.py`, which turns every private key and switch off, so your `.env` doesn't change a test result.

| Variable | Default | What it does |
|---|---|---|
| `DJANGO_DEBUG` | `true` in `settings.env`, `false` in the image | Django's `DEBUG`. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Django's `ALLOWED_HOSTS`. |
| `DJANGO_SECRET_KEY` | empty | Django's `SECRET_KEY` (`.env`). Empty: a fixed insecure key with `DEBUG` on, a generated one in `DATA_DIR/secret_key` with it off. |
| `APP_PORT`, `APP_HOST` | `8000`, `127.0.0.1` | Where `manage.py serve` listens. |
| `DATA_DIR` | `storage` | The database, uploads, sandboxes and relay snapshots. |
| `SURVEYJS_SERVICE_URL` | `http://localhost:3010` | The SurveyJS service (`docker compose up -d surveyjs`). In Compose, the app uses `http://surveyjs:3000`. |
| `VALIDATE_RESPONSES` | `false` | Validate Responses: `examples/views/validate_response.py` replaces `examples/views/save_response.py`. |
| `LINT_DEFINITIONS` | `false` | Lint JSON Schemas: `examples/views/lint_definition.py` replaces `examples/views/creator_load_save.py`. |
| `SURVEYJS_AI_PROVIDER`, `SURVEYJS_AI_MODEL`, `SURVEYJS_OLLAMA_BASE_URL`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | empty | Extract Responses from Documents: Compose passes them to the service as `AI_PROVIDER`, `AI_MODEL` and `OLLAMA_BASE_URL` (`openai`, `anthropic` or `ollama`). The app reads them only for the page's banner. |
| `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` | OpenAI, empty, `gpt-4o-mini` | Translate with AI: any OpenAI-compatible `/chat/completions` endpoint. Without a key, `/api/translate` answers `501`. |
| `SURVEYJS_LICENSE_KEY` | empty | Calls `setLicenseKey()` on every page. Without it, the commercial components show a licence banner. The service at its pinned revision ignores it, so server PDFs carry the SurveyJS alert banner. |
| `RELAY_URL`, `EDIT_RELAY_URL` | empty | The relays' origin when a proxy serves `/ws/` elsewhere, for example `wss://example.com`. Empty: the page's own origin. |
| `DEMO_MODE` | `false` | The hosted demo's visitor sandboxes (below). |
| `SURVEYJS_BUILD` | from git | The `<branch>@<commit>` the pages show as "Running …". Deploys set it themselves. |
| `SURVEYJS_DOCS`, `SURVEYJS_GITHUB` | the Django docs page, this repository | Where the pages link. |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | The proxies uvicorn trusts for `X-Forwarded-*` (see [Behind a proxy](#behind-a-proxy)). |

## The examples

<!-- steps:start (generated by `python manage.py readme` from surveyjs-integration.json) -->
| Example | Run | Server | Client | Page | Licence |
|---|---|---|---|---|---|
| [Save Responses](https://surveyjs.io/documentation/backend-integration-django#save-responses) | `/examples/save-response` | [`examples/views/save_response.py`](examples/views/save_response.py) | [`shared/client/save-response.js`](shared/client/save-response.js) | [`templates/examples/save-response.html`](templates/examples/save-response.html) | MIT |
| [Load JSON Schemas, Variables, and Answers](https://surveyjs.io/documentation/backend-integration-django#load-json-schemas-variables-and-answers) | `/examples/load-definition-variables-data` | [`examples/views/load_definition_variables_data.py`](examples/views/load_definition_variables_data.py) | [`shared/client/load-definition-variables-data.js`](shared/client/load-definition-variables-data.js) | [`templates/examples/load-definition-variables-data.html`](templates/examples/load-definition-variables-data.html) | MIT |
| [Resume Progress](https://surveyjs.io/documentation/backend-integration-django#resume-progress) | `/examples/resume-progress` | [`examples/views/resume_progress.py`](examples/views/resume_progress.py) | [`shared/client/resume-progress.js`](shared/client/resume-progress.js) | [`templates/examples/resume-progress.html`](templates/examples/resume-progress.html) | MIT |
| [Store Files Separately](https://surveyjs.io/documentation/backend-integration-django#store-files-separately) | `/examples/store-files` | [`examples/views/store_files.py`](examples/views/store_files.py) | [`shared/client/store-files.js`](shared/client/store-files.js) | [`templates/examples/store-files.html`](templates/examples/store-files.html) | MIT |
| [Load Choices from Web](https://surveyjs.io/documentation/backend-integration-django#load-choices-from-web) | `/examples/choices-from-web` | [`examples/views/choices_from_web.py`](examples/views/choices_from_web.py) | [`shared/client/choices-from-web.js`](shared/client/choices-from-web.js) | [`templates/examples/choices-from-web.html`](templates/examples/choices-from-web.html) | MIT |
| [Async Calculations and Validation](https://surveyjs.io/documentation/backend-integration-django#async-calculations-and-validation) | `/examples/async-functions` | [`examples/views/async_functions.py`](examples/views/async_functions.py) | [`shared/client/async-functions.js`](shared/client/async-functions.js) | [`templates/examples/async-functions.html`](templates/examples/async-functions.html) | MIT |
| [Use Relational Storage](https://surveyjs.io/documentation/backend-integration-django#use-relational-storage) | `/examples/relational-storage` | [`examples/views/relational_storage.py`](examples/views/relational_storage.py) | [`shared/client/relational-storage.js`](shared/client/relational-storage.js) | [`templates/examples/relational-storage.html`](templates/examples/relational-storage.html) | MIT |
| [Fill Forms Together](https://surveyjs.io/documentation/backend-integration-django#fill-forms-together) | `/examples/fill-together` | [`examples/consumers/fill_together.py`](examples/consumers/fill_together.py) | [`shared/client/fill-together.js`](shared/client/fill-together.js) | [`templates/examples/fill-together.html`](templates/examples/fill-together.html) | MIT |
| [Analyze Results with Dashboard](https://surveyjs.io/documentation/backend-integration-django#analyze-results-with-dashboard) | `/examples/dashboard` | [`examples/views/dashboard.py`](examples/views/dashboard.py) | [`shared/client/dashboard.js`](shared/client/dashboard.js) | [`templates/examples/dashboard.html`](templates/examples/dashboard.html) | Commercial client |
| [Load and Save Form JSON Schemas](https://surveyjs.io/documentation/backend-integration-django#load-and-save-form-json-schemas) | `/examples/creator-load-save` | [`examples/views/creator_load_save.py`](examples/views/creator_load_save.py) | [`shared/client/creator-load-save.js`](shared/client/creator-load-save.js) | [`templates/examples/creator-load-save.html`](templates/examples/creator-load-save.html) | Commercial client |
| [Upload Files](https://surveyjs.io/documentation/backend-integration-django#upload-files) | `/examples/creator-uploads` | [`examples/views/store_files.py`](examples/views/store_files.py) | [`shared/client/creator-uploads.js`](shared/client/creator-uploads.js) | [`templates/examples/creator-uploads.html`](templates/examples/creator-uploads.html) | Commercial client |
| [Translate with AI](https://surveyjs.io/documentation/backend-integration-django#translate-with-ai) | `/examples/ai-translation` | [`examples/views/ai_translation.py`](examples/views/ai_translation.py) | [`shared/client/ai-translation.js`](shared/client/ai-translation.js) | [`templates/examples/ai-translation.html`](templates/examples/ai-translation.html) | Commercial client, needs an AI provider |
| [Variable Presets](https://surveyjs.io/documentation/backend-integration-django#variable-presets) | `/examples/variable-presets` | [`examples/views/variable_presets.py`](examples/views/variable_presets.py) | [`shared/client/variable-presets.js`](shared/client/variable-presets.js) | [`templates/examples/variable-presets.html`](templates/examples/variable-presets.html) | Commercial client |
| [Edit Forms Together](https://surveyjs.io/documentation/backend-integration-django#edit-forms-together) | `/examples/edit-together` | [`examples/consumers/edit_together.py`](examples/consumers/edit_together.py) | [`shared/client/edit-together.js`](shared/client/edit-together.js) | [`templates/examples/edit-together.html`](templates/examples/edit-together.html) | Commercial client |
| [Validate Responses](https://surveyjs.io/documentation/backend-integration-django#validate-responses) | `/examples/validate-response` | [`examples/views/validate_response.py`](examples/views/validate_response.py) | [`shared/client/validate-response.js`](shared/client/validate-response.js) | [`templates/examples/validate-response.html`](templates/examples/validate-response.html) | MIT |
| [Lint JSON Schemas](https://surveyjs.io/documentation/backend-integration-django#lint-json-schemas) | `/examples/lint-definition` | [`examples/views/lint_definition.py`](examples/views/lint_definition.py) | [`shared/client/lint-definition.js`](shared/client/lint-definition.js) | [`templates/examples/lint-definition.html`](templates/examples/lint-definition.html) | MIT |
| [Generate PDFs](https://surveyjs.io/documentation/backend-integration-django#generate-pdfs) | `/examples/server-pdf` | [`examples/views/server_pdf.py`](examples/views/server_pdf.py) | [`shared/client/server-pdf.js`](shared/client/server-pdf.js) | [`templates/examples/server-pdf.html`](templates/examples/server-pdf.html) | Commercial |
| [Extract Responses from Documents](https://surveyjs.io/documentation/backend-integration-django#extract-responses-from-documents) | `/examples/extract-from-paper` | [`examples/views/extract_from_paper.py`](examples/views/extract_from_paper.py) | [`shared/client/extract-from-paper.js`](shared/client/extract-from-paper.js) | [`templates/examples/extract-from-paper.html`](templates/examples/extract-from-paper.html) | MIT, needs an AI provider |
<!-- steps:end -->

## Where each example lives

Each example is two or three files you can read on their own. The full explanation is in [the docs](https://surveyjs.io/documentation/backend-integration-django).

- `examples/views/<snake_slug>.py`: the example's function views, the server code the docs show. `examples/urls.py` lists every path once, in the docs' order, and `by_method()` (`examples/routing.py`) picks the view per HTTP method where two examples share a path (`POST /api/responses` and the dashboard's `GET`; `GET /api/forms/<id>` and Creator's `PUT`). The switches pick `validate_response.py` or `save_response.py`, and `lint_definition.py` or `creator_load_save.py`, when `examples/urls.py` is imported.
- `examples/consumers/fill_together.py` and `edit_together.py`: the two relays, as Channels `AsyncWebsocketConsumer`s routed in `examples/routing.py`; their rooms are in `examples/relay/`.
- `shared/client/<slug>.js`: the example's client code, a plain ES module, the same file on every platform.
- `templates/examples/<slug>.html`: the example's page (Django templates): its description, the "Try this" list and the component.
- `examples/models.py`: one model per table (see [Database](#database)), the custom `User` and the `edit_forms` permission.
- `examples/integration/`: small helpers some views call, so the code the docs show stays about SurveyJS. They aren't demo code:
  - `stored_json.py`: `read_json()`, `dumps()`, `created_at()` and `insert_response()` (see below).
  - `surveyjs_service.py`: `SurveyJsService.post()` with its timeouts, the 503 and 504 when the service doesn't answer, and the logging.
  - `ai_translation.py`: the call to your OpenAI-compatible provider.
  - `http.py`, `file_type.py`: the outbound HTTP client, and file types by their first bytes.
- `examples/db.py` (`JsonExtract`, the sandbox router), `examples/auth.py` (`can()`, `can_read_file()`), `examples/middleware.py` (the `{ error }` shape, CSRF for the pages only) and `config/settings.py`.

To copy an example, copy its view module, the helpers it imports and its `path()` lines. The code the docs show is cut from these files between `# region sjs:<slug>.server` and `# endregion` (and `// #region sjs:<slug>.client` in the client modules). `surveyjs-integration.json` lists every example's files and regions; `python manage.py surveyjs_check` verifies them.

### Shared files

`shared/` holds what every platform repository uses byte for byte: the client modules, the form definitions, samples and seed data, the page UI (`shared/ui/`), and the contract, smoke and browser tests. It is a copy of [`surveyjs-php-laravel`](https://github.com/surveyjs/surveyjs-php-laravel)'s `shared/` at the commit in `shared/UPSTREAM`; `python manage.py surveyjs_check` compares it with `shared/SHA256SUMS`. Don't edit it here: send a fix to that repository, then copy `shared/` again. `.gitattributes` keeps it in LF on Windows checkouts too, or every hash would fail. WhiteNoise serves exactly four of its folders, `/shared/client/`, `/shared/definitions/`, `/shared/samples/` and `/shared/ui/` (`examples/static.py`).

### Editing example descriptions

The text in an example's Description panel is the `description` block of `templates/examples/<slug>.html`. It can hold several paragraphs, links and other markup:

```django
{% block description %}
    <p>Your custom description.</p>
    <p>More details with <strong>formatting</strong>.</p>
{% endblock %}
```

The "Try this" list is the `try` block; the layout is `templates/layouts/example.html`. The catalog cards use `need` from `surveyjs-integration.json` for their "Use when" text. After editing a template, rebuild the stylesheet (see [Front end](#front-end)) if you used a Tailwind class no other template uses.

### Storing JSON exactly as it arrives

A response, a definition, saved progress and variable presets are each one JSON document, stored as text and returned as stored.

- **The raw body.** The storing views call `read_json(request)` (`examples/integration/stored_json.py`): `json.loads(request.body)`, which keeps every key, `{}`, `[{}]`, `None`, `""`, whitespace inside strings and `1.0`. A comment in each view says why. They never read `request.POST`: after it, Django refuses `request.body`.
- **`NaN` is refused.** Python's `json.loads` accepts `NaN`, `Infinity` and `-Infinity`; JSON doesn't, so `read_json()` rejects them with `400 { "error": "The request body is not valid JSON" }`, like any other body that isn't JSON.
- **`ensure_ascii=False`.** `dumps()` stores `"naïve — 東京"` as it is, not as `\u` escapes, with compact separators; `1.0` stays `1.0`.
- **`TextField`, not `JSONField`.** A `JSONField` decodes the document on every read and encodes it again on every save; a `TextField` keeps the text the app wrote, and the dashboard returns the stored strings joined, not re-encoded.
- **Dates are strings.** `created_at` is a `CharField` holding ISO 8601 UTC without fractions (`2026-11-19T12:00:00Z`, written by `created_at()`), so the dashboard's date filters are string comparisons. A `DateTimeField` would store `2026-11-19 12:00:00.000000` in SQLite.
- Under `/api/`, every error is `{ "error": … }`, also Django's own (`examples/middleware.py`): the resolver's 404, a 405 (with `Allow`), a body over `DATA_UPLOAD_MAX_MEMORY_SIZE` as `413`, a view that raises as `500`, with `DEBUG` on or off. Outside `/api/`, Django's error pages stay (`templates/404.html`, `500.html`).

### Database

SQLite through the Django ORM, in `DATA_DIR/database.sqlite`, in WAL mode, with `transaction_mode = "IMMEDIATE"`, so two concurrent saves of one form wait for each other instead of failing.

- **One model per table**, in `examples/models.py`: `Form`, `Response`, `Progress`, `File`, `Office`, `Customer`, `ShippingRate`, `Claim` and `VariablePreset`, plus the custom `User` (`AbstractUser` with a `plan`). Each keeps the docs' table and column names (`db_table`, the field names), so the SQL you see in `sqlite3` or a query log reads as the docs do.
- **Documents are strings** (`TextField`, above). A field inside a document is read with SQLite's `json_extract()`, through one `Func` in `examples/db.py`, so the claim-request filter stays an ORM query: `.annotate(email=JsonExtract("data", "$.customer_email")).filter(email=user.email)`.
- **Migrations.** `examples/migrations/0001_initial.py` creates the tables; `python manage.py migrate` applies it, and a `post_migrate` receiver (`examples/seed.py`) seeds them from `shared/seed/*.json`, adding any missing form to an existing database. CI runs `makemigrations --check`.
- **Inspect the file** with `sqlite3 storage/database.sqlite` (`.tables`, `SELECT data FROM responses ORDER BY id DESC LIMIT 1;`), or `python manage.py dbshell`.
- **On Postgres**, change `DATABASES` (`django.db.backends.postgresql`). `json_extract()` is SQLite's: on Postgres, read the field with `->>` (a `Func` with `template = "%(expressions)s ->> 'customer_email'"`), or add a `JSONField` copy of the column and filter with `KT("data_json__customer_email")`, keeping the `TextField` as the stored original.

### Sync and async views

Under ASGI, Django runs every sync view, and every sync-only middleware, on one shared thread (`sync_to_async(thread_sensitive=True)`). A sync view that waited 120 seconds on the network would hold every other sync view up. So:

- Views that wait on the network (the SurveyJS service, the AI provider, restcountries.com) are `async def` and use `httpx2.AsyncClient` (`examples/integration/http.py`), with the async ORM (`afirst()`, `acreate()`, `aupdate_or_create()`) and `await request.auser()`.
- Views that only touch SQLite are `def`. Use Relational Storage is one of them: it needs `transaction.atomic()`, which has no async form.
- Every middleware of this project runs in the mode of what it wraps (`SyncAndAsyncMiddleware` in `examples/middleware.py`), so an async view stays on the event loop. WhiteNoise's own middleware is sync only; `examples/static.py` answers in both modes.
- Never call a blocking HTTP client from an `async def` view: one extraction would stall every visitor.

### CSRF and the API

`CsrfViewMiddleware` refuses every `POST`, `PUT` and `DELETE` that carries no token, and the shared client modules send none. `examples/middleware.py` therefore replaces it with `ApiCsrfViewMiddleware`, which skips paths under `/api/`; the pages keep CSRF protection. That is safe enough for this demo because the demo user's cookie is `SameSite=Lax`: a cross-site `POST` arrives signed out, and signed-out saves are refused. A real app keeps `CsrfViewMiddleware` for its API too, and sends the `csrftoken` cookie's value as an `X-CSRFToken` header from its `fetch()` calls. The views carry no `@csrf_exempt`, so the code the docs show is what you copy.

## How data works in the demo

Locally, everyone shares one SQLite database, `storage/database.sqlite` (delete `storage/` to start over).

On a hosted demo (`DEMO_MODE=true`), each visitor gets a private copy of the seeded database and uploads folder, chosen by a `demo_sid` cookie, and kept until it has been unused for 24 hours. `demo/sandbox.py`, an ASGI middleware around the whole app, copies the database with SQLite's backup API on first use, registers it as a database alias, and sets the context variable the ORM's router (`examples/db.py`) returns, so the views don't change. An hourly task in the app removes unused sandboxes (`config/lifespan.py`); a host with cron can run `python manage.py prune_sandboxes` instead. The "Open a second window" link in Fill Forms Together and Edit Forms Together carries the sandbox id (`?join=`), so whoever opens it works in the same copy and the same relay rooms. The demo also caps uploads at 5 MB and the AI examples at 20 calls per visitor per day, counted in Django's cache. None of this is in the example code. The sandbox needs ASGI (`manage.py serve`), not `runserver`.

## Front end

- The pages are Django templates (`templates/`), autoescaped. Each page diffs against its Blade source in the reference repository in template syntax only, with the Tailwind class strings unchanged; what a Blade view computes in `@php` (records, `?form`, `?version`) is in `examples/pages.py`. Inline JSON (the page config, `window.FORM_DEFINITION`, `window.FORM_VARIABLES`) goes through `json_script`, which escapes `<`, `>` and `&`, so a `</script>` in a definition can't end the script; no value from the database or the request is ever `|safe`. The import map, which `json_script` can't write, comes from the `{% import_map %}` tag (`examples/templatetags/frontend.py`).
- The site stylesheet is Tailwind CSS v4 without Preflight: `styles/site.css` imports `tailwindcss/theme.css` (static), `tailwindcss/utilities.css` and `shared/ui/theme.css`. `npm run css` builds it into `static/css/site.css` with `@tailwindcss/cli`. The output is committed, so running the app never needs Node; CI rebuilds it and fails on a difference. WhiteNoise serves `/static/`. The [Tailwind standalone binary](https://tailwindcss.com/blog/standalone-cli) builds the same file without Node: `tailwindcss -i styles/site.css -o static/css/site.css --minify`.
- The client code is the shared ES modules in `shared/client/` and `shared/ui/`, loaded unchanged with `<script type="module">` and an import map (`examples/frontend.py`). No Python package carries SurveyJS's browser builds, so every specifier points to unpkg: the SurveyJS packages at the version in `shared/surveyjs-version.json` (`fesm/*.mjs`), and `chart.js`, `@kurkle/color`, `lodash-es` and highlight.js at pinned versions. There is no bundler.
- To self-host them, copy each package's `fesm/` files (and the CSS the pages load) into `static/vendor/<package>@<version>/` and point `UNPKG` in `examples/frontend.py` at `/static/vendor`. Don't mix the script-tag builds (`survey.core.js` and friends) with the ES modules on one page: they would load SurveyJS twice.
- WhiteNoise sends `.js` and `.mjs` as `text/javascript` from its own table. Python's `mimetypes`, which `django.views.static.serve` uses, reads the Windows registry, where `.mjs` can be `text/plain`, and browsers refuse to run a module served that way.
- The forms use the SurveyJS Tailwind adapter (`survey-core/themes/adapters/tailwind4.css`). No page calls `applyTheme()`: its inline styles would override the adapter.

## Not on Django?

[surveyjs-python-fastapi](https://github.com/surveyjs/surveyjs-python-fastapi) has every example on FastAPI, and its README shows the Flask version. Save Responses as a FastAPI route, reading the raw body for the same reason:

```python
@router.post("/api/responses", status_code=201)
async def save_response(request: Request) -> dict[str, int]:
    body = json.loads(await request.body())   # not a Pydantic model: it would drop the keys it doesn't declare
    if not isinstance(body, dict) or "formId" not in body or "data" not in body:
        raise HTTPException(400, "Expected { formId, data }")
    return {"id": insert_response(body["formId"], body["data"])}
```

## Using Django REST Framework?

The views are plain Django, so they move into DRF in a few lines. Save Responses as an `@api_view`:

```python
@api_view(["POST"])
def save(request: Request) -> Response:
    body = json.loads(request.body)   # the raw body, not request.data
    if not isinstance(body, dict) or "formId" not in body or "data" not in body:
        return Response({"error": "Expected { formId, data }"}, status=400)
    return Response({"id": insert_response(body["formId"], body["data"])}, status=201)
```

This repository doesn't use DRF: it adds a dependency, and its parsers hand you `request.data`, a parsed `dict` that is fine to validate but not to store, because the stored document must be the one the client sent. Read `request.body` before anything touches `request.data` (DRF reads the stream once). DRF's own errors are `{ "detail": … }`; a custom `EXCEPTION_HANDLER` that renames `detail` to `error` gives the `{ error }` shape every platform uses.

## Browse the tables in the admin

The admin isn't installed: no page needs it. To browse the tables with it:

1. Add `django.contrib.admin`, `django.contrib.sessions` and `django.contrib.messages` to `INSTALLED_APPS`, and `SessionMiddleware`, `AuthenticationMiddleware` and `MessageMiddleware` to `MIDDLEWARE` (in place of `demo.users.DemoUserMiddleware`), with the `auth` and `messages` context processors, then run `python manage.py migrate`.
2. Register the models in `examples/admin.py`: `admin.site.register([Form, Response, Progress, File, Claim, VariablePreset])`.
3. Add `path("admin/", admin.site.urls)` to `config/urls.py`, then `python manage.py createsuperuser`.

## Disclaimer

These examples must not be used as a real service as they are. They don't cover authentication, authorization, user management, access levels and other security aspects of a real survey service. The places where real checks go are marked:

- `can(user, "edit-forms")` and `can_read_file(user, file)` in `examples/auth.py`: who may save definitions and presets (the `examples.edit_forms` permission), and who may read an uploaded file.
- `demo/users.py`'s `DemoUserMiddleware` and `DemoUserWebSocketMiddleware`: the demo signs in Alice or Bob from a `demo_user` cookie. Your app uses `django.contrib.sessions` with `AuthenticationMiddleware`, and Channels' `AuthMiddlewareStack` for the relays; the views and consumers read `request.user` and `scope["user"]` either way.

When you copy an example into your app, leave out the demo-only code: the `demo/` app (with its `MIDDLEWARE` lines, its `INSTALLED_APPS` line, its `config/urls.py` include and its `DemoSandbox` and `DemoUserWebSocketMiddleware` wrappers in `config/asgi.py`), `examples/pages.py`, `examples/frontend.py`, `examples/static.py`, `examples/relay/room_key.py`'s sandbox keys, `templates/`, `shared/ui/` (the page frame, its tabs and highlighting, the fonts and site images) and `shared/client/host.js` (its `mountSurvey()` is one line: `renderSurvey(survey, element)` from `survey-js-ui`).
