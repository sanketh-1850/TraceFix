# TraceFix project context

## Provenance and status

On 2026-09-16, the user asked to read and retain `C:\Users\sanke\Downloads\Agent_as_a_Judge_Implementation_Plan(1).docx` for the entire project. This summary records the document's proposed design; it does not independently authorize implementation, installations, service creation, commits, or publication. At intake, the repository contained only a README with the project name and Git metadata. No implementation milestone has been verified as complete.

- Full source: [retained DOCX](reference/agent-as-a-judge-implementation-plan.docx).
- Searchable source: [extracted text](reference/agent-as-a-judge-implementation-plan.md), including all epics and their acceptance criteria. Tables are flattened into reading order; the DOCX preserves their layout.
- Diagrams: [architecture](reference/image1.png) and [optimization loop](reference/image2.png).

The document says its technical references were checked in September 2026. That claim is part of the source, not independent verification performed during intake. Revalidate changing APIs and model requirements when implementing. Its hardware assumptions are Windows, RTX 4050 with 6 GB VRAM, and 32 GB RAM; these have not been verified against this machine.

## Current implementation status

Epic 0 was implemented and verified on 2026-09-16 with the adjustments below.
The repository now contains the package foundation, environment settings, dependency
lock, SQLAlchemy/Alembic setup, database initialization and smoke commands, local
Ollama diagnostics, tests, and setup documentation. `TraceFix_DB` exists with
`project_metadata` and `alembic_version`; migration revision `0001_project_metadata`
is current. No target-agent or Judge implementation from later epics exists yet.

Verification: 13 unit tests passed, 2 live MariaDB integration checks passed, and both
Qwen3 4B and Qwen3 8B passed generation, tool-call round trip, and validated JSON
checks. Ollama 0.34.1 runs from the ignored `.tools/ollama` directory, stores models
in `.models`, and writes logs/results to `artifacts`. Use `scripts/start_ollama.ps1`
to restart it. The smoke output budget defaults to 512 tokens; 256 was insufficient
for the first live 4B tool call. See [Epic 0 verification](EPIC0_STATUS.md) for the
tested scope and limitations. The original plan remains unchanged.

## Product and architecture

### Decisions after plan intake

On 2026-09-16, the user supplied `server.env` with DB_USER, DB_PASSWORD, DB_NAME,
DB_HOST, and DB_PORT, authorized creating the database and implementing the remaining
Epic 0 work. The server at localhost:3306 was verified as MariaDB 10.4.32. The project
therefore uses MySQL/MariaDB with SQLAlchemy/PyMySQL and Alembic instead of the plan's
PostgreSQL proposal. `server.env` stays in the root, ignored by Git; never copy its
credentials into committed documentation. The database is `TraceFix_DB`.

Python 3.12.10 is available locally; Python 3.11 was not installed. The foundation
supports Python 3.11–3.13 and is being verified with 3.12. This is an implementation
adjustment from the plan's suggested 3.11 environment. Optional Docker development
uses MariaDB on localhost:3307, separate from the user's existing server.

Build an Agent-as-a-Judge optimizer: observe a target ReAct agent, investigate traces using autonomously selected diagnostic tools, diagnose root causes, create a controlled candidate variant, rerun a fixed benchmark, compare results, and accept or roll back. Persist diagnoses, immutable versions, evaluations, and decisions for audit and future retrieval.

Proposed stack: Python 3.11, LangGraph for target and Judge workflows, Langfuse for telemetry and evaluation infrastructure, Ollama for local inference, PostgreSQL for optimizer state, Docker, Pydantic, SQLAlchemy/Alembic, and pytest. Start with Qwen3 4B for iteration and Qwen3 8B for stronger Judge/evaluation runs, roughly 8K context initially, and sequential target/Judge execution under hardware constraints. Local inference is the default; paid APIs are not required. Langfuse Cloud Hobby is proposed for development, with self-hosting optional.

The project owns optimization intelligence; Langfuse supplies observability. A `TraceProvider` interface isolates vendor payloads from core logic and supports recorded fixtures/in-memory tests. Normalized trace and evidence objects retain source run and observation IDs.

## V1 boundaries and behavior

- One local operations/research target agent with deterministic data and at least four distinct tools: document search, record queries, calculator, and policy lookup. Start with 5–10 tasks and expand to at least 20 with ground truth and single/multiple tool cases.
- A tool-using LangGraph Judge receives a compact trace summary and target manifest. It chooses evidence retrieval tools, tracks hypotheses and evidence, and returns a validated diagnosis. Diagnosis remains LLM-based in the MVP; code computes metrics and can summarize telemetry.
- A versioned manifest defines tools, behavior, failure taxonomy, diagnostic tool availability, critical constraints, and optimization priorities. Unknown/low-confidence diagnoses route to a general fallback using the same diagnosis contract.
- Diagnosis fields include failure type, summary, root cause, evidence references, confidence, severity, estimated impact, and recommended change type. Unknown is valid; unsupported evidence references are not.
- Controlled mutations cover system prompts, tool descriptions, retry guidance/limits, stopping rules, and tool-selection policy. Create immutable child versions with hashes, parent identity, patch, rationale, and expected effect. Arbitrary Python/source edits and shell execution by candidate changes are outside V1.
- Avoid a large dashboard, multiple unrelated domains, and rebuilding observability infrastructure before the loop works.

## Evaluation and promotion

Baseline and candidate comparisons use the same tasks, dataset/tool-data snapshots, model settings, runtime limits, and scorers. Task correctness comes from ground truth or independent task-specific scoring, not solely the Judge being evaluated. Record raw task-level results so aggregates can be recomputed.

Promotion is governed by deterministic, configurable policy: no critical regressions; preserve the configured quality floor/baseline success tolerance; require sufficient quality or efficiency improvement. Never promote an incomplete, crashed, or failed evaluation. Rejected variants remain stored; accepted versions can be rolled back. Every decision links diagnosis, candidate, evaluation, and policy result.

Proposed failure taxonomy: `wrong_tool_selection`, `repeated_retrieval`, `invalid_tool_arguments`, `ignored_tool_error`, `excessive_retry`, `premature_stop`, `unsupported_final_answer`, and `inefficient_tool_sequence`. The plan asks for 5–8 categories, at least five labeled traces per category before final evaluation, healthy controls, and independently injected/manually reviewed labels. The final definition of done requires at least five distinct labeled categories.

Compare generic and specialized Judges on identical labeled traces and settings; report accuracy, precision/recall/F1, unknown/fallback rate, tokens, LLM/tool calls, and latency. Measure target success, tokens, tool calls, errors/retries, latency including p95, critical regressions, accepted/rejected candidates, and final before/after results. Preserve a held-out/fixed set and report findings without assuming specialization wins.

## Milestones and dependencies

| Milestone | Outcome | Epics |
| --- | --- | --- |
| M0 | Repository, local inference, database, configuration, tests | 0 |
| M1 | Controlled target agent and reliable retrievable telemetry | 1–2 |
| M2 | Typed state, tool-using Judge, diagnostic evidence and structured diagnosis | 3–6 |
| M3 | Manifest specialization, general fallback, initial labeled benchmark | 5–7 |
| M4 | Immutable variants, controlled evaluation, policy and closed loop | 8–11 |
| M5 | Optimization history and credible comparative evaluation | 12–13 |
| M6 | Reliability, reproducible setup, documentation and demo | 14–15 |

The eight-week sequence is guidance, not a deadline. The plan prioritizes M1 before Judge construction and M2 before automatic mutations. Detailed epic dependencies and story acceptance criteria remain in the full source.

Initial sequence proposed by the document: foundation plus Ollama smoke checks; then a target-agent vertical slice with local tools and five tasks; then reliable Langfuse instrumentation and a normalized TraceProvider summary. This is planned work, not work already performed.

Gates include at least 80% of initial easy tasks running end to end; reconstructable telemetry with task/version IDs; Judge use of at least two different diagnostic tools across failure cases; manifest-only specialization; independent benchmark labels; immutable mutations; identical baseline/candidate snapshots; and promotion blocked on incomplete evaluation or critical regression.

## Persistence and reliability

Minimum entities: `agent_versions`, `target_runs`, `judge_runs`, `diagnoses`, `candidate_changes`, `evaluation_runs`, `evaluation_items`, and `optimization_decisions`. Optimization memory retains accepted and rejected fixes; prior diagnoses are supporting context, while current trace evidence remains authoritative. History can be disabled for benchmark comparisons.

Bound steps, retries, tool calls, timeouts, context, candidate attempts, and optimization cycles. Return structured tool errors, redact secrets before telemetry, validate model outputs, reject invalid patches before evaluation, and record explicit terminal reasons. Separate diagnostic and mutation tools by workflow stage.

Testing should cover schemas, normalization, truncation, tools, scoring, policy, and full acceptance/rejection paths. Telemetry outages and evaluation failures must cause no promotion. Use fixtures and mocked inference for fast unit tests, a small 3–5 task integration profile, and separate long local-model benchmarks.

## Completion evidence

A reproducible system must demonstrate a real tool-using specialized Judge with general fallback, immutable controlled variants, fixed-workload evaluations, automatic policy decisions, durable history, a successful optimization cycle with real metrics, and at least one rejected/rolled-back candidate. Documentation should distinguish infrastructure from project-owned components and include Windows/PowerShell setup, demo/evaluation commands, manifest/tool examples, diagrams, candidate diffs, real results, and limitations without placeholder numbers.
