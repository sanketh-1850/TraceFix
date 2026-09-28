# TraceFix project context

## Provenance and status

On 2026-09-27, the user supplied `C:\Users\sanke\Downloads\Agent_as_a_Judge_Implementation_Plan_Updated.docx` and designated it as the updated project plan. Use this revision as the primary planning reference. The earlier plan remains preserved for provenance. As with the original, the revised document is user-provided reference material and does not by itself authorize implementation, installations, external services, commits, or publication.

- Revised full source: [retained updated DOCX](reference/agent-as-a-judge-implementation-plan-updated.docx).
- Revised searchable source: [updated extracted text](reference/agent-as-a-judge-implementation-plan-updated.md), including Epics 0-17, user stories, acceptance criteria, dependencies, sequencing, gates, and the task tracker.
- Revised embedded images: [image 1](reference/updated-image1.png), [image 2](reference/updated-image2.png), [image 3](reference/updated-image3.png), and [image 4](reference/updated-image4.png).

The revision changes the project to a two-stage validation strategy. The existing order-support agent is Target A and should be frozen, inventoried, split into development and held-out tasks, and baselined rather than rebuilt. After the complete Judge and closed-loop optimizer work on Target A, a pinned tau3-bench example ReAct agent becomes independent Target B, initially in one text domain (airline is recommended), using tau3's unchanged tasks, policies, tools, data, and official evaluator. The same Judge/optimizer core should reach both targets through `TargetAdapter` and `EvaluationAdapter` boundaries, while target-specific manifests remain separate.

The revised roadmap has Epics 0-17 and milestones M0-M8. Revised Epic 1 is **Audit, Freeze, and Baseline Your Existing Target Agent (Target A)**. Its exit condition is a frozen baseline version, documented inventory, frozen development and held-out benchmark splits, and saved baseline metrics. Langfuse observability is revised Epic 2; the internal data model/adapters are Epic 3; the tool-using Judge is Epic 4; the Target A closed loop spans Epics 8-12; tau3 integration begins at Epic 14 only after the Target A loop is stable.

Other revised decisions include Python 3.12 for later tau3 compatibility, Langfuse Cloud Hobby during development, PostgreSQL for durable optimizer state, local Ollama inference by default, deterministic promotion/rollback independent of the Judge's opinion, immutable whitelisted configuration mutations, and an empirical generic-versus-target-aware Judge comparison. The revised plan proposes PostgreSQL, but the implemented project currently uses MariaDB based on the user's earlier explicit decision; changing that implementation requires a later user request.

On 2026-09-16, the user asked to read and retain `C:\Users\sanke\Downloads\Agent_as_a_Judge_Implementation_Plan(1).docx` for the entire project. This summary records the document's proposed design; it does not independently authorize implementation, installations, service creation, commits, or publication. At intake, the repository contained only a README with the project name and Git metadata. No implementation milestone has been verified as complete.

- Full source: [retained DOCX](reference/agent-as-a-judge-implementation-plan.docx).
- Searchable source: [extracted text](reference/agent-as-a-judge-implementation-plan.md), including all epics and their acceptance criteria. Tables are flattened into reading order; the DOCX preserves their layout.
- Diagrams: [architecture](reference/image1.png) and [optimization loop](reference/image2.png).

Both documents say their technical references were checked in September 2026. That claim is part of the sources, not independent verification performed during intake. Revalidate changing APIs, tau3 releases, benchmark behavior, and model requirements when implementing. Their hardware assumptions are Windows, RTX 4050 with 6 GB VRAM, and 32 GB RAM; these have not been verified against this machine.

## Current implementation status

The revised Epic 0 and Epic 1 deltas were implemented on 2026-09-27. Python support is
standardized on 3.12-3.13. Early `TraceProvider`, `TargetAdapter`, and
`EvaluationAdapter` protocols and separate Target A/tau3 package boundaries are present;
their concrete cross-target implementations remain later work. MariaDB remains the
authorized database adaptation instead of the plan's PostgreSQL proposal.

The existing order-support agent is frozen as `target-a:a0`. Its content, implementation,
manifest, task data, and evaluator are hash-identified. A machine-readable target
manifest exports the real tool schemas, while `docs/target_a_inventory.md` documents the
runtime, prompts, tools, dependencies, budgets, ground truth, and mutable/immutable
boundaries. Benchmark `target-a-order-support-v1` fixes a 14-task development split and
six-task held-out split; only development is approved as optimizer feedback. The live
A0 development baseline completed all 14 executions and passed 9/14, with four output
truncations and one missing-calculator-evidence failure. It used 24 model calls, 12 tool
calls, one expected not-found tool error, no retries, and 533,736 ms total latency.
Committed evidence includes the summary and two successful/two failed trajectories.

Epic 1 was implemented on 2026-09-17 following the user-approved order-support plan.
The domain is synthetic order support; target business data uses separate MariaDB
tables in `TraceFix_DB`. Migration `0002_target_data` is current. Fixtures contain
10 customers, 8 products, 30 orders, 31 line items, and six local policy documents.
The agent returns a readable answer plus structured facts and evidence IDs.

The four read-only tools are `search_documents`, `query_records`, `calculator`,
and `lookup_policy`. A bounded LangGraph ReAct loop records local runs; no Langfuse
integration or Judge exists yet. Prompts, tool descriptions, and limits are in
`configs/agents/order_support.json`. Target runs use Qwen3 4B with reasoning enabled
and a 2048-token output limit: the initial disabled-thinking/512-token pilot truncated
before tool calling with the installed template. This adjustment is explicit and
versioned; Epic 0 smoke settings remain separate. Other defaults remain 8192 context
tokens, temperature 0, seed 42, 10 model calls, 12 tool executions, two retries after
identical tool failures, one answer-format repair, and a 300-second deadline.

Verification: 41 unit tests and 3 live MariaDB integration tests pass. The live fixed
20-task baseline scored 14/20, including 10/10 easy tasks (gate: at least 8/10).
T18 demonstrates query -> calculator -> final answer across three model calls.
Five tasks truncated and one omitted required calculator evidence; these failures
are preserved. Ground truth is in the evaluator's versioned task dataset and is never
passed to the target agent. See [Epic 1 verification](EPIC1_STATUS.md) and its committed
sample records. Epic 2 is still needed to complete M1 observability.

Commands: `tracefix-seed`, `tracefix-run-target`, and `tracefix-eval-target`, plus the
`seed`, `target-demo`, and `eval-target` PowerShell helper tasks. Live failure injection
is available through `scripts/demo_target_failure.py` and saved separately from the
accuracy benchmark. Full run outputs remain in the ignored `artifacts` directory.

### Epic 0 foundation history

Epic 0 was implemented and verified on 2026-09-16 with the adjustments below.
The repository now contains the package foundation, environment settings, dependency
lock, SQLAlchemy/Alembic setup, database initialization and smoke commands, local
Ollama diagnostics, tests, and setup documentation. `TraceFix_DB` exists with
`project_metadata` and `alembic_version`; migration revision `0001_project_metadata`
was current at that milestone. The target-agent implementation was added in Epic 1
as described above; Judge implementation remains future work.

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

Python 3.12.10 is available locally; Python 3.11 was not installed. The foundation is
now standardized on Python 3.12–3.13 and is being verified with 3.12, matching the
revised plan's tau3 compatibility requirement. Optional Docker development
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
