# Epic 0 verification

Verified on 2026-09-16 in the TraceFix workspace.

Epic 0 is implemented and verified for the existing MariaDB server and Python 3.12
environment, with the deviations from the reference plan documented below.

## Implemented foundation

- Editable Python package with separate target, Judge, diagnostics, telemetry,
  optimization, evaluation, persistence, and common modules.
- Environment-driven settings, protected secret values, `server.env` excluded from
  Git, an example env file, logging, bounded dependency ranges, and a resolved
  development dependency lock file.
- PowerShell setup/test/database/inference commands and setup documentation.
- MySQL/MariaDB database creation, SQLAlchemy metadata model, Alembic migrations,
  and a committed-record smoke check that cleans up its own record.
- Ollama generation, validated tool-call round trip, and structured JSON diagnostics;
  opt-in live integration tests separate from the default offline test suite.

## Verified results

| Check | Result |
| --- | --- |
| Unit tests | 13 passed; 4 live integration cases excluded by default |
| Live database tests | 2 passed: record round trip and disposable-database migration round trip |
| Database | `TraceFix_DB` created on MariaDB 10.4.32 at localhost:3306 |
| Schema | `0001_project_metadata` at head; `project_metadata` and `alembic_version` tables |
| Smoke cleanup | No metadata rows remain after diagnostics |
| Migration behavior | Upgrade is repeatable; downgrade/re-upgrade verified on disposable MariaDB and SQLite databases |
| Dependency installation | Installed into `.venv`; `pip check` passed |
| Required libraries | LangGraph, LangChain Ollama, Langfuse, Ollama, SQLAlchemy, Alembic import successfully |
| Static checks | Ruff and PowerShell syntax checks passed |
| Optional Docker configuration | Compose validation passed; container not started because the existing database is used |
| Local inference runtime | Official Ollama 0.34.1 portable archive verified against the release SHA-256 list |
| Qwen3 4B | Generation, tool-call round trip, and structured JSON passed |
| Qwen3 8B | Generation, tool-call round trip, and structured JSON passed |

Detailed local inference metadata is written to the ignored `artifacts/` directory.
The output cap is 512 tokens after the first live 4B tool request exceeded 256 tokens.
The successful 4B tool request used 332 output tokens; truncated generations are
explicitly rejected. These are setup smoke checks, not Judge or target benchmarks.

## Adjustments from the reference plan

The user's supplied phpMyAdmin connection is backed by MariaDB, so it replaces
PostgreSQL for this implementation. Python 3.12.10 is used because 3.11 was not
installed; the package declares Python 3.11–3.13 compatibility, with runtime validation
performed on 3.12 only. The optional Docker profile uses MariaDB on localhost:3307
and has not been exercised as a running container.

The original implementation plan is unchanged. Later epics remain unimplemented;
the initial table holds project metadata only.
