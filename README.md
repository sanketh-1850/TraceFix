# TraceFix

TraceFix is a planned target-aware Agent-as-a-Judge optimizer. It will investigate
agent traces, propose controlled configuration changes, and evaluate candidates
before promotion. The current implementation covers the Epic 0 foundation;
target-agent and Judge behavior belong to later epics.

See [Epic 0 verification](docs/EPIC0_STATUS.md) for completed checks and environment
adjustments.

## Local setup

Use Python 3.11 or 3.12 (this workspace uses 3.12.10). From the repository root in
PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.lock
.venv/Scripts/python.exe -m pip install --no-deps -e .
if (-not (Test-Path server.env)) { Copy-Item .env.example server.env }
```

The lock file records the versions resolved and tested on Windows/Python 3.12.
For development with updated versions within the declared ranges, use
`./scripts/dev.ps1 setup` instead of the two pip commands above.

Keep database credentials in `server.env`, which is ignored by Git. Process
environment variables override the file; `TRACEFIX_ENV_FILE` selects an alternate
file. Settings load from the repository root even when a command runs elsewhere.
`.env.example` lists supported settings without real credentials.

## Database

This project uses the user's existing MySQL/MariaDB server, visible in phpMyAdmin.
That supersedes the original plan's PostgreSQL proposal. The default endpoint is
`127.0.0.1:3306`; the configured database is `TraceFix_DB`.

```powershell
./scripts/dev.ps1 db-init
./scripts/dev.ps1 db-smoke
.venv/Scripts/python.exe -m tracefix.persistence.cli current
```

`db-init` creates the configured database if missing and applies Alembic migrations.
The initial migration creates only `project_metadata`; Alembic also maintains its
version table. `db-smoke` commits a unique test record, reads it through a new
session, and deletes only that record. It leaves existing records intact.

Schema changes go in `migrations/versions/`. To generate a migration after editing
models, use `.venv/Scripts/alembic.exe revision --autogenerate -m "description"` and
review it before applying. Downgrades are available through Alembic; the initial
downgrade drops the metadata table and its contents, so use it only on a disposable
database. Default unit tests exercise migration upgrade/downgrade on temporary SQLite.

Optional Docker alternative (requires a running Docker Desktop engine):

```powershell
docker compose --env-file server.env -f docker-compose.dev.yml up -d --wait
$env:DB_PORT = '3307'
./scripts/dev.ps1 db-init
./scripts/dev.ps1 db-smoke
Remove-Item Env:DB_PORT
```

The optional MariaDB container binds to localhost port 3307 to avoid the existing
server on 3306. It uses `DB_NAME`/`DB_PASSWORD` from the explicitly supplied env file,
initializes a root login, and retains its data in a Docker volume. Its empty-password
option matches the supplied local development configuration. Container initialization
settings apply only to a new volume. This container is not needed for the existing server.

## Ollama

Use the official [Windows Ollama runtime](https://docs.ollama.com/windows).
With an installed CLI, start `ollama serve` if the service is not already running,
then download the two models:

```powershell
ollama pull qwen3:4b
ollama pull qwen3:8b
./scripts/dev.ps1 ollama-smoke
```

For the project-local portable runtime in `.tools/ollama`, use
`./scripts/start_ollama.ps1` and then:

```powershell
.tools/ollama/ollama.exe pull qwen3:4b
.tools/ollama/ollama.exe pull qwen3:8b
.venv/Scripts/python.exe scripts/smoke_ollama.py --all-models
```

The start script stores models under the ignored `.models` directory and logs under
`artifacts/`. The portable binary is local setup state, not committed to the project;
a clean clone needs an official Ollama installation or extracted Windows archive.

The smoke script checks normal generation, a validated addition tool call and return
trip, and Pydantic-validated JSON output. It uses 8192 context tokens, temperature 0,
seed 42, disabled thinking, a configurable 512-token output cap, and a per-request timeout. Models
run sequentially and unload after requests to limit memory pressure. Model settings,
timestamps, tokens, and per-call latency are saved in `artifacts/ollama-smoke.json`.
This uses Ollama's [tool calling](https://docs.ollama.com/capabilities/tool-calling)
and [structured output](https://docs.ollama.com/capabilities/structured-outputs) APIs.

For a single model:

```powershell
.venv/Scripts/python.exe scripts/smoke_ollama.py --model qwen3:4b
```

If a check fails, confirm the server is running at `OLLAMA_HOST`, the model is listed
by `ollama list`, and the request fits `OLLAMA_TIMEOUT_SECONDS`. Database command errors
deliberately omit raw exceptions to avoid exposing credentials; check service access,
the env file, and whether migrations have been applied.

## Tests and checks

```powershell
./scripts/dev.ps1 test
.venv/Scripts/python.exe -m ruff check src tests migrations scripts
.venv/Scripts/python.exe -m pip check
```

Default tests need neither a live database nor Ollama. They cover credential handling,
configuration precedence, identifier validation, migration round trips, record isolation,
and mocked inference success/failure paths. Live checks are opt-in:

```powershell
.venv/Scripts/python.exe -m pytest -m integration
```

## Layout and plan

`src/tracefix/` separates `target_agent`, `judge`, `diagnostics`, `telemetry`,
`optimization`, `evaluation`, `persistence`, and `common`. The first six are package
boundaries reserved for future epics. Manual diagnostics live in `scripts/`; automated
tests live in `tests/unit/` and `tests/integration/`.

See [project context](docs/PROJECT_CONTEXT.md) for current decisions and the
[retained implementation plan](docs/reference/agent-as-a-judge-implementation-plan.md)
for detailed acceptance criteria. The original document is preserved unchanged.
