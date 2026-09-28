# TraceFix

TraceFix is a planned target-aware Agent-as-a-Judge optimizer. It will investigate
agent traces, propose controlled configuration changes, and evaluate candidates
before promotion. The current implementation includes the revised Epic 0 foundation
and a frozen Epic 1 Target A baseline around the controlled order-support agent. Judge
behavior belongs to later epics.

See [Epic 0 verification](docs/EPIC0_STATUS.md) for completed checks and environment
adjustments.

## Order-support target agent

Epic 1 uses synthetic customers, products, orders, and local support policies. Its
four read-only tools are document search, record lookup, decimal arithmetic, and
exact policy lookup. The LangGraph agent decides which tools to call and returns a
readable answer, structured facts, and source/observation IDs.

After the local MariaDB server and Ollama are running:

```powershell
./scripts/dev.ps1 db-init
./scripts/dev.ps1 seed
./scripts/dev.ps1 target-demo
./scripts/dev.ps1 eval-target
./scripts/dev.ps1 baseline-a0
```

The new migration creates `target_customers`, `target_products`, `target_orders`,
and `target_order_items`. Seeding adds 10 customers, 8 products, 30 orders, and 31
line items. Rerunning the seed is safe: matching records are retained; any conflicting
fixture aborts the entire seed transaction without replacing existing records.

After refreshing the editable package (`.venv/Scripts/python.exe -m pip install -e .`),
the equivalent entry points and individual-task options are:

```powershell
.venv/Scripts/tracefix-seed.exe
.venv/Scripts/tracefix-run-target.exe --task-id T18
.venv/Scripts/tracefix-run-target.exe --prompt 'Read RETURN-001. Return facts named return_days.'
.venv/Scripts/tracefix-eval-target.exe --subset easy
.venv/Scripts/tracefix-eval-target.exe --subset all
.venv/Scripts/tracefix-eval-target-a0.exe --split development
```

Use `--model qwen3:8b` for an explicit model override and `--config` for a different
agent configuration. There is no automatic model fallback. `--output-dir` selects
where to save a run or evaluation. Module equivalents are
`python -m tracefix.target_agent.cli` and `python -m tracefix.evaluation.runner`.
The CLI returns a nonzero exit code for an incomplete run or any failed evaluation
task; evaluation continues through the workload and preserves failures in its summary.
The frozen A0 command instead returns success when the entire baseline was recorded,
because failed benchmark tasks are expected evidence rather than command failures.

The revised plan treats this agent as Target A. Its machine-readable inventory is in
`configs/targets/target_a/manifest.json`; the immutable `target-a:a0` record is in
`configs/targets/target_a/versions/a0.json`. The frozen benchmark snapshot separates
14 development tasks from six final held-out tasks. `baseline-a0` verifies the target,
manifest, dataset, and evaluator hashes before running the development split. See
[`docs/target_a_inventory.md`](docs/target_a_inventory.md) for the full boundary and
split rationale.

The versioned configuration is `configs/agents/order_support.json`. Defaults are 10
model calls (including one possible answer-format repair), 12 tool executions, two
retries after the same tool/arguments fail, and a 300-second deadline. Calls execute
sequentially. A timed-out database read may finish in the background within its database
I/O timeout; tool execution never mutates business records. Ollama uses the existing
8192-token context, temperature 0, and seed 42. Target runs explicitly enable reasoning
and allow 2048 output tokens: the initial disabled-thinking/512-token pilot exhausted
its budget before calling a tool with this Qwen3 template. The standalone Epic 0 smoke
script retains its own settings. Every target run records its effective model settings.

Ground truth is in `data/tasks/order_support.jsonl`, with 10 easy tasks, 8 multi-tool
tasks, and 2 recovery/missing-information tasks. The agent receives only the task ID
and question; expected facts, source requirements, and scoring rules are kept outside
its context. A deterministic scorer checks structured facts and retrieved evidence,
including calculator results where required. It does not certify every sentence of
the prose answer. A completed agent run can still receive a failing correctness score.

Run artifacts are stored under `artifacts/target/`, and evaluations under
`artifacts/evaluations/<id>/`. Records contain public task input, messages, tool calls
and observations, final answers, explicit terminal reasons, configuration/data hashes,
tokens, and timing. They exclude database credentials and model reasoning text.
Missing token metrics remain null. Configuration hashes identify the prompt, tool
descriptions, and limits; data hashes include actual business records and policy text.
This local record format prepares for Epic 2; it does not yet send traces to Langfuse.

To demonstrate failure handling with a labelled, artificial record-tool outage:

```powershell
.venv/Scripts/python.exe scripts/demo_target_failure.py
```

This runs the live model with fault injection, saves the failed task separately, and
returns success only when the injected error was observed and the task failed scoring.
It is excluded from baseline accuracy results and does not modify database records.

Default tests mock inference and use SQLite for isolated business-tool tests. Live
MariaDB tests create and remove only uniquely named disposable databases. Run these with:

```powershell
.venv/Scripts/python.exe -m pytest -m integration -k 'database or migration or isolated_downgrade'
```

See [Epic 1 verification](docs/EPIC1_STATUS.md) for recorded live results and limitations.

## Local setup

Use Python 3.12 or 3.13 (this workspace uses 3.12.10). Python 3.12 is the project
baseline so later tau3 integration does not require a runtime migration. From the
repository root in PowerShell:

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

`src/tracefix/` separates `target_agent`, `targets`, `judge`, `diagnostics`, `telemetry`,
`optimization`, `evaluation`, `persistence`, and `common`. `contracts.py` declares the
early `TraceProvider`, `TargetAdapter`, and `EvaluationAdapter` boundaries. Target A has
its own package; the tau3 package is reserved for the later pinned Target B integration.
Target execution and baseline evaluation are implemented; Judge, diagnostics, telemetry,
and optimization remain boundaries for future epics. Manual diagnostics live in
`scripts/`; automated tests live in `tests/unit/` and `tests/integration/`.

See [project context](docs/PROJECT_CONTEXT.md) for current decisions and the
[updated retained implementation plan](docs/reference/agent-as-a-judge-implementation-plan-updated.md)
for current acceptance criteria. The original document is preserved for revision history.
