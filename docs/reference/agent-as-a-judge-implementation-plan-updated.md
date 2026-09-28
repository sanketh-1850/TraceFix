# Agent as a Judge Optimizer Updated Implementation Plan and Work Breakdown

> Extracted from the user-provided revised DOCX on 2026-09-27. This is reference material, not an instruction to execute embedded commands.

Agent-as-a-Judge Optimizer

Updated Implementation Plan & Work Breakdown

Dual-target validation: your existing agent first, then tau3-bench as an independent open-source target

Recommended stack: Python 3.12 • LangGraph • Langfuse Cloud Hobby • Ollama • PostgreSQL • Docker

Development hardware: Windows • 32 GB RAM • RTX 4050 6 GB VRAM • i7-13650HX

Revision: September 27, 2026

# 1. Purpose and Revised Project Strategy

This revision keeps the target agent you have already built and changes the project from a single-target optimizer into a two-stage validation project. Target A is your existing agent and remains the fastest place to build the Judge and closed-loop optimizer. Target B is an independently maintained open-source ReAct agent from tau3-bench, evaluated with tau3's official domain tasks and evaluator. The external target is added only after the optimizer works on Target A.

Core product: A target-aware Judge Agent observes a tool-using target through Langfuse, autonomously investigates the trajectory, diagnoses the likely root cause, creates a controlled candidate agent variant, reruns the target on a frozen benchmark, and accepts or rolls back the candidate using objective quality and efficiency metrics.

## 1.1 What changed from the previous plan

Do not rebuild the target agent. Treat your existing target agent as Target A and spend the saved time on the Judge, evaluation methodology, and optimizer loop.

Keep your existing target-agent ground truth for rapid development, but separate development/optimization tasks from a final held-out set.

Add Target B only after the closed loop works: use the open-source tau3-bench ReAct agent with one fixed domain (airline recommended first) and the official tau3 evaluator.

Introduce a TargetAdapter/EvaluationAdapter layer so the same Judge framework can operate on both targets without hardcoding target-specific execution logic into the Judge graph.

Compare a generic Judge against target-aware Judge configurations using the same model and the same traces. Do not assume specialization is better; measure diagnosis quality and inference overhead.

Use Langfuse Cloud Hobby during development. Self-hosting is optional and should not delay the agentic-AI work.

Use Python 3.12 for the main environment because current tau3-bench requires Python >=3.12 and <3.14.

## 1.2 Scope for the first complete version

Target A: your already-built tool-using target agent, with its existing tools, data, policies/instructions, and task-level ground truth.

One target-aware Judge Agent implemented as a LangGraph stateful workflow that chooses diagnostic tools rather than receiving a preassembled trace dump.

Langfuse Cloud Hobby for target/Judge observability, with a provider abstraction so optimizer logic does not depend directly on Langfuse payloads.

LLM-based diagnosis in the MVP. Normal code may normalize telemetry, calculate metrics, enforce schemas, and apply acceptance rules, but diagnosis remains agentic.

A manifest/profile per target describing tools, behavioral expectations, failure taxonomy, relevant Judge tools, allowed mutations, and optimization priorities.

Controlled target mutations: system/reasoning prompts, tool-use guidance, retry/stop guidance, and other explicitly whitelisted configuration. No arbitrary source-code rewriting in the MVP.

Immutable candidate versions, frozen benchmark snapshots, before/after evaluation, and automatic accept/rollback.

Generic Judge mode plus target-aware Judge mode, evaluated head-to-head on the same labeled traces.

Target B: tau3-bench ReAct agent in one fixed domain after Target A is working, with tau3 tasks/policies/tools/evaluator left unchanged.

Persistent optimization history in PostgreSQL and a reproducible final report.

## 1.3 Two-target validation strategy

| Track | Purpose | What you control | Ground truth / evaluator |
| --- | --- | --- | --- |
| Target A - Existing custom agent | Build quickly, debug Judge behavior, develop the optimizer loop. | Agent implementation/config, task split, Judge, mutations, optimizer. | Your existing task ground truth. Freeze a held-out subset before optimization. |
| Target B - tau3 ReAct agent | Independent external validation that the optimizer is not only tuned to your own agent. | Judge integration, allowed ReAct-agent configuration changes, instrumentation. | Official tau3 tasks, domain policy/tools/data, and evaluator. Do not modify them. |

The strongest final claim is not "my Judge beat LangSmith". It is: "I built a reusable closed-loop optimizer, showed measurable improvement on my own target, and then validated the same framework against an independently developed open-source agent and benchmark."

## 1.4 Explicit non-goals for the MVP

Do not replace Langfuse with a custom observability platform.

Do not rebuild Target A unless a specific defect blocks instrumentation or versioning.

Do not modify tau3 task definitions, domain policy, database, tool semantics, or official evaluator to make a candidate look better.

Do not optimize against the final held-out evaluation set.

Do not support every tau3 domain initially. Start with one text domain; add a second domain only as a stretch goal.

Do not allow arbitrary code edits, shell execution, or unrestricted self-modification by the Judge in the first complete version.

Do not require paid model APIs. Local Ollama remains the default; tau3 uses LiteLLM, which supports Ollama/local providers, but compatibility must be verified in an integration spike.

Do not build a large custom dashboard before the optimizer loop and evaluations work.

# 2. End-State Architecture

Figure 1. Revised architecture. Target A accelerates development; Target B supplies external validation. Both targets flow through the same Judge/optimizer interfaces while keeping their evaluators independent.

## 2.1 Closed-loop behavior

Figure 2. A candidate is never promoted because the Judge says it is better. It must be rerun against the same frozen benchmark and pass the deterministic acceptance policy.

## 2.2 Ownership boundaries

| Component | Owner / source | Role in the project |
| --- | --- | --- |
| Target A | You | Existing target agent used for rapid optimizer development. |
| Target A ground truth | You, frozen before optimization | Fast local evaluation; final held-out subset protects against overfitting. |
| Target B ReAct agent | tau3-bench open-source example | Independent target that proves the optimizer can adapt beyond your own agent. |
| Target B domain + evaluator | tau3-bench | External policy, tools, data, tasks, and official scoring. |
| Langfuse | Third-party observability infrastructure | Trace/observation storage, token/latency metadata, run correlation. |
| Judge / Optimizer | You | Agentic investigation, diagnosis, proposed mutation, experiment control. |
| Acceptance / rollback policy | You | Deterministic promotion logic; Judge cannot self-certify success. |

# 3. Architecture Decisions to Lock Before Coding

| ID | Decision | Reason |
| --- | --- | --- |
| D1 | Keep your existing target agent as Target A. | It is already built; rebuilding it adds little signal compared with improving the Judge and evaluation design. |
| D2 | Use tau3-bench ReAct agent as Target B only after the core loop works. | External validation is valuable, but tau3 integration should not block the MVP. |
| D3 | Use LangGraph for the Judge/optimizer orchestration. | The Judge needs explicit state, tool selection, branching, bounded loops, mutation/evaluation phases, and controlled termination. |
| D4 | Use Langfuse Cloud Hobby during development. | It removes local ClickHouse/Redis/MinIO overhead while preserving the same tracing abstraction; self-hosting remains optional. |
| D5 | Use a TraceProvider abstraction. | The Judge consumes normalized telemetry rather than vendor-specific Langfuse objects. This makes tests easier and leaves room for other trace backends. |
| D6 | Use a TargetAdapter + EvaluationAdapter abstraction. | Target A and tau3 run differently. The optimizer should call one stable interface for versioning, execution, and scoring. |
| D7 | Keep diagnosis LLM-based in the MVP. | Your research question is whether target-aware context/rubrics/tools improve an LLM Judge. Deterministic diagnosis can be an ablation later, not a prerequisite. |
| D8 | Use Ollama/local models by default. | Avoid API cost. Use 4B for iteration and 8B for serious Judge runs; run target and Judge sequentially on the RTX 4050. |
| D9 | Use PostgreSQL for durable optimizer state. | Keep agent versions, diagnoses, experiments, and promotion history independent of Langfuse. |
| D10 | Only mutate explicitly whitelisted agent configuration. | Safe, inspectable prompt/policy changes are easier to version, compare, and rollback than arbitrary code generation. |
| D11 | Freeze evaluation inputs and evaluators per experiment. | Baseline and candidate must see the same tasks, model settings, user simulator settings, seed/trials, and scoring logic. |
| D12 | Separate optimization/dev sets from final held-out sets. | Prevents the Judge from repeatedly tuning to the exact tasks used for the final improvement number. |
| D13 | Pin tau3-bench to an exact release/tag (v1.0.1 or later chosen pin). | The project has had task/evaluator fixes; a fixed version is required for reproducible scores. |
| D14 | Start tau3 external validation with a text domain, preferably airline. | It has meaningful tools/policies without the extra retrieval stack of banking_knowledge or voice infrastructure. |
| D15 | Treat specialized-Judge superiority as a hypothesis, not a premise. | Report accuracy, recall/F1, tokens, tool calls, latency, UNKNOWN/fallback rate, and downstream target improvement. |

# 4. Delivery Milestones and Recommended Order

| Milestone | What must work | Epics |
| --- | --- | --- |
| M0 - Foundation | Repo, Python 3.12, Ollama, Postgres, tests, configuration, and basic adapters. | 0 |
| M1 - Frozen Target A Baseline | Existing target inventory is documented, benchmark split is frozen, baseline metrics and traces exist. | 1-2 |
| M2 - Diagnostic Judge | Judge loads a target trace, chooses diagnostic tools, collects evidence, and emits schema-valid diagnosis. | 3-6 |
| M3 - Target-Aware Judging | Manifest changes failure taxonomy/tool access; generic fallback exists; labeled diagnosis set exists. | 5-7 |
| M4 - Closed Loop on Target A | Versioned candidate, fixed rerun, comparison, accept/rollback, and bounded multi-cycle optimization all work. | 8-12 |
| M5 - Internal Evidence | Generic vs specialized Judge and Target A before/after results are reproducible on held-out data. | 13 |
| M6 - External tau3 Target | Pinned tau3 ReAct agent runs one fixed domain locally, is traced, and is scored by the official evaluator. | 14 |
| M7 - Cross-Target Validation | Same optimizer interfaces operate on Target A and Target B; specialized manifests remain separate. | 15 |
| M8 - Portfolio-Ready | Reliability tests, README, architecture, results tables, limitations, and reproducible demo are complete. | 16-17 |

Do not parallelize tau3 integration with the first Judge implementation. Finish the complete Target A loop first. External validation is useful only after there is a stable optimizer to validate.

Epic 0: Repository, Environment, and Engineering Baseline

| Goal | Create a reproducible development environment that supports the existing target, the Judge, and later tau3 integration. |
| --- | --- |
| Dependencies | None |
| Exit milestone | A clean clone can install dependencies, call the local model, connect to Postgres, and run tests. |

US-0.1 - Create the revised repository structure

User story: As the developer, I need clean boundaries between target integrations, the Judge, telemetry, optimization, evaluation, and persistence.

Acceptance criteria

Repository has separate packages for judge, diagnostics, telemetry, optimization, persistence, Target A adapter, and tau3 adapter.

Configuration is environment-driven; secrets are not committed.

A single fast command runs unit tests.

Python version is standardized on 3.12 to remain compatible with the current tau3-bench requirements.

Technical tasks

Initialize/clean the repository and create a Python 3.12 environment (uv recommended because current tau3 uses uv).

Create pyproject.toml with separated core/dev/tau3 optional dependency groups if practical.

Add .env.example, .gitignore, logging configuration, and PowerShell helper commands.

Create interfaces early: TraceProvider, TargetAdapter, EvaluationAdapter; implementations can initially be stubs.

Deliverables

Repository skeleton

pytest smoke test

Environment/setup documentation

US-0.2 - Verify local Ollama workflow

User story: As the developer, I need reliable zero-cost local inference before building the Judge loop.

Acceptance criteria

Qwen3 4B can be invoked from Python.

Tool calling works on a minimal example.

Structured JSON output validates with Pydantic.

Qwen3 8B can run for stronger Judge tests even if some layers/cache spill to system RAM.

Technical tasks

Install/update Ollama and pull qwen3:4b and qwen3:8b.

Create scripts/smoke_ollama.py for chat, tool-call, and structured-output checks.

Start around an 8K context for 8B; increase only after measuring memory and latency.

Record model, context, temperature, and inference settings with every experiment.

US-0.3 - Start PostgreSQL and migrations

User story: As the optimizer, I need durable state that is independent of observability storage.

Acceptance criteria

PostgreSQL starts from Docker Compose.

Alembic (or equivalent) can create/drop the schema.

Application can insert/read a smoke record.

Technical tasks

Add a PostgreSQL service to docker-compose.dev.yml.

Create SQLAlchemy models/migrations for the first metadata tables.

Keep Langfuse telemetry and optimizer database responsibilities separate.

Epic 1: Audit, Freeze, and Baseline Your Existing Target Agent (Target A)

| Goal | Turn the already-built target agent into a reproducible system-under-test instead of rebuilding it. |
| --- | --- |
| Dependencies | Epic 0 |
| Exit milestone | Target A has a frozen baseline version, documented tools/configuration, a development benchmark split, a held-out split, and baseline metrics. |

If Target A currently lacks enough failures to study, do not intentionally weaken the benchmark. Create separate controlled fault-injected agent variants later in Epic 7 so the original benchmark remains honest.

US-1.1 - Inventory the existing target agent

User story: As the optimizer developer, I need an exact map of Target A so the Judge can reason about the correct tools and failure modes.

Acceptance criteria

Document model, orchestration framework, system/reasoning prompt, tool names/schemas/descriptions, stop/retry logic, and external dependencies.

Document which settings are safe for the optimizer to mutate and which are immutable.

Document the existing task data and ground-truth scoring path.

Technical tasks

Create docs/target_a_inventory.md from the real code, not assumptions.

Export tool schemas and descriptions into a machine-readable target manifest.

Identify state-changing versus read-only tools and any policy/order constraints.

Record current configuration as AgentVersion A0 with a content hash.

US-1.2 - Freeze a baseline and benchmark snapshot

User story: As the evaluator, I need a fixed baseline so later improvements are attributable to optimizer changes.

Acceptance criteria

Baseline code/config and benchmark data receive immutable version identifiers.

Evaluation tasks are split before optimization into dev/optimization and final held-out sets.

Scorer behavior is tested on known pass/fail examples.

No held-out labels/results are used by the optimizer.

Technical tasks

Create dataset_version and evaluator_version identifiers.

Choose a split strategy; stratify by tool/failure/difficulty when labels exist.

Snapshot prompts/tool descriptions/model configuration used by A0.

Create a command that reruns A0 on the exact same benchmark snapshot.

US-1.3 - Collect the Target A baseline

User story: As the project owner, I need a quantitative starting point and real failures for Judge development.

Acceptance criteria

Baseline report includes task success, token usage, tool calls, tool errors/retries, latency, and failure count.

At least several successful and failed trajectories are saved and traceable.

Every result can be mapped back to task ID and agent version.

Technical tasks

Run the dev/optimization split at fixed model settings.

Persist per-task outputs plus aggregate metrics.

Select representative failures for initial Judge development.

Do not optimize yet; first verify that the same baseline can be reproduced within expected stochastic variance.

Epic 2: Langfuse Observability, Trace Identity, and Provider Boundary

| Goal | Capture target/Judge behavior in Langfuse while exposing normalized telemetry to the optimizer through your own interface. |
| --- | --- |
| Dependencies | Epics 0-1 |
| Exit milestone | Every Target A run is traceable and the Judge can retrieve compact normalized evidence without importing Langfuse SDK objects. |

US-2.1 - Instrument Target A with Langfuse Cloud Hobby

User story: As the Judge, I need detailed execution traces for diagnosis.

Acceptance criteria

LLM calls, tool calls, important inputs/outputs, latency, and available token metadata are visible in Langfuse.

Trace metadata includes target_id, task_id, agent_version_id, model_id, dataset_version, and run_id.

Sensitive secrets or irrelevant large payloads are filtered before logging.

Technical tasks

Configure a Langfuse Cloud Hobby project for development.

Instrument Target A at the orchestration/model/tool boundaries appropriate to its framework.

Create one shared metadata helper so identifiers are consistent across every target.

Add flush/shutdown logic for CLI/evaluation scripts.

US-2.2 - Implement TraceProvider

User story: As the optimizer, I need one telemetry contract independent of Langfuse payload formats.

Acceptance criteria

Judge code imports TraceProvider interfaces, not Langfuse client types.

LangfuseTraceProvider can retrieve trace summaries, tool calls/observations, and metric summaries required by diagnostics.

An in-memory/fake provider supports unit tests.

Technical tasks

Define get_trace_summary(), list_tool_calls(), inspect_observation(), get_run_metrics(), list_runs().

Normalize payloads into internal Pydantic models.

Write contract tests against captured fixture traces.

Document which trace fields are authoritative and which may be missing depending on model integration.

US-2.3 - Instrument Judge runs separately

User story: As the evaluator of the evaluator, I need to measure the Judge itself.

Acceptance criteria

Judge trace IDs are distinct from target trace IDs but linked by metadata.

Judge tokens, diagnostic tool calls, latency, fallback usage, and final diagnosis are recordable.

Generic and specialized Judge modes are tagged consistently.

Technical tasks

Add judge_run_id, mode, target_id, source_target_run_id, manifest_version to metadata.

Capture diagnostic tool spans and final structured diagnosis.

Ensure the Judge does not ingest its own telemetry as target evidence by mistake.

Epic 3: Internal Data Model, Adapters, and Judge State

| Goal | Create stable internal contracts so the Judge can work across your target and tau3 later. |
| --- | --- |
| Dependencies | Epics 0-2 |
| Exit milestone | Typed models represent target profiles, traces, evidence, diagnoses, candidates, evaluation results, and optimizer state without target-specific code in the Judge graph. |

US-3.1 - Define normalized telemetry/evidence models

User story: As the Judge, I need compact evidence objects instead of raw traces.

Acceptance criteria

TraceSummary, ToolCallSummary, ObservationExcerpt, MetricSummary, and RunComparison are typed.

Every evidence object carries source run/observation identifiers.

Large outputs are truncated/summarized before entering LLM context.

Technical tasks

Create src/common/schemas.py models.

Define explicit truncation limits and provenance fields.

Store raw payload references outside the Judge prompt when possible.

US-3.2 - Define TargetAdapter and EvaluationAdapter

User story: As the optimizer, I need the same execution interface for different target agents.

Acceptance criteria

TargetAdapter can load a version, run a task, create/apply an allowed candidate configuration, and return run identifiers.

EvaluationAdapter can score a run/version against a named dataset split and return normalized metrics.

Target A implementation exists before tau3 is added.

Technical tasks

Define abstract/protocol methods for load_version, create_candidate, run_task/run_suite, get_mutable_surface, and rollback.

Define evaluation result schema with task-level + aggregate fields.

Implement TargetAAdapter and TargetAEvaluationAdapter.

US-3.3 - Define JudgeGraphState

User story: As LangGraph, I need explicit state for investigation and optimization decisions.

Acceptance criteria

State contains target/run identity, manifest, evidence, hypotheses, diagnosis, candidate metadata, evaluation results, budgets, and terminal reason.

State does not carry unbounded raw histories.

Serialization works for persistence/checkpointing.

Technical tasks

Create JudgeGraphState/TypedDict or Pydantic state model.

Add budget counters: model calls, diagnostic calls, max evidence bytes/tokens, optimization cycle.

Define terminal reasons such as DIAGNOSED, UNKNOWN, ACCEPTED, ROLLED_BACK, BUDGET_EXHAUSTED, EVAL_FAILED.

Epic 4: Build the Tool-Using Judge Agent

| Goal | Create the meta-agent that autonomously decides what evidence to inspect and when it has enough information to diagnose. |
| --- | --- |
| Dependencies | Epic 3 |
| Exit milestone | Given a target run ID, the Judge can choose diagnostic tools, gather evidence, form/update hypotheses, stop within budget, and return a schema-valid diagnosis. |

US-4.1 - Implement the investigation loop in LangGraph

User story: As the Judge, I need to choose the next diagnostic action based on evidence rather than follow a fixed pipeline.

Acceptance criteria

Different failures cause different diagnostic-tool paths.

Judge can loop through multiple evidence requests.

Max-step and max-tool-call budgets always terminate the graph.

Technical tasks

Create nodes for load_context, judge_reason, execute_diagnostic_tool, update_evidence, finalize_diagnosis, and fallback routing.

Use structured tool calls and Pydantic validation.

Record hypothesis/evidence summaries between steps instead of raw chain-of-thought.

Test at least three trajectories that cause distinct tool choices.

US-4.2 - Define the diagnosis contract

User story: As downstream optimization code, I need a diagnosis that is structured enough to act on and evaluate.

Acceptance criteria

Diagnosis includes failure_type, concise root_cause, evidence references, confidence, severity, and recommended change category.

UNKNOWN is a valid outcome.

The Judge cannot invent evidence identifiers.

Technical tasks

Create Diagnosis schema and validation.

Require evidence IDs/run IDs for factual diagnostic claims.

Add confidence calibration fields and explicit missing-information notes.

US-4.3 - Add resource and context controls

User story: As the developer, I need the Judge to be usable on a 6 GB GPU without uncontrolled context growth.

Acceptance criteria

Raw full traces are not inserted into the prompt by default.

Diagnostic results have strict size limits.

Judge records tokens/tool calls/latency for later generic-vs-specialized comparison.

Technical tasks

Set per-tool output limits.

Start with 4B for rapid development, 8B for serious benchmark runs.

Tune context after measurements, not theoretical maximums.

Epic 5: Target-Aware Judge Configuration and Generic Fallback

| Goal | Make specialization configurable per target/domain instead of hardcoding rules into the graph. |
| --- | --- |
| Dependencies | Epic 4 |
| Exit milestone | Changing only a target manifest changes Judge failure categories, relevant tools, target rules, allowed mutations, and priorities; generic mode remains available. |

US-5.1 - Define the target manifest schema

User story: As the Judge, I need a concise machine-readable description of the system I am evaluating.

Acceptance criteria

Manifest covers tool purposes/schemas, behavioral rules, failure taxonomy, relevant Judge tools, mutable surface, and optimization priorities.

Manifest is versioned independently from agent versions.

Invalid references to unknown tools/failure types fail validation.

Technical tasks

Implement TargetManifest and validator.

Generate Target A manifest from the real target inventory.

Keep the manifest concise enough to fit local-model context.

US-5.2 - Implement specialized and generic Judge modes

User story: As the experiment owner, I need controlled Judge configurations to test whether target-aware specialization actually helps.

Acceptance criteria

Specialized mode receives target-specific rubric/rules and only relevant diagnostic tools.

Generic mode uses the same LLM/model settings but a general failure taxonomy and broader toolset.

Both modes emit the same Diagnosis schema.

Technical tasks

Create separate prompt/config builders.

Keep model, temperature, context policy, and evaluation data fixed when comparing modes.

Log the manifest/prompt/tool-registry versions for every Judge run.

US-5.3 - Route uncertain cases to fallback

User story: As the Judge, I need a way to handle failures outside the specialized taxonomy.

Acceptance criteria

Low-confidence/UNKNOWN specialized diagnoses can invoke the generic fallback within a bounded budget.

Fallback invocation is measurable.

Fallback does not overwrite the original specialized evidence trail.

Technical tasks

Define fallback threshold/policy.

Persist both specialized and fallback outputs.

Measure whether fallback improves recall at acceptable token/tool-call cost.

Epic 6: Diagnostic Tool Registry

| Goal | Give the Judge narrow evidence-retrieval tools so it can investigate instead of receiving everything at once. |
| --- | --- |
| Dependencies | Epics 2-5 |
| Exit milestone | The Judge can investigate target behavior through a stable registry of compact tools with clear provenance and target-aware availability. |

US-6.1 - Implement trace/trajectory inspection tools

User story: As the Judge, I need to inspect only the relevant parts of a target run.

Acceptance criteria

Tools exist for trace summary, tool-call list, individual call inspection, message/observation excerpt, token/latency analysis, and run comparison.

Outputs are bounded and cite their source IDs.

Tools fail cleanly on missing telemetry.

Technical tasks

Implement get_trace_summary(), list_tool_calls(), inspect_tool_call(), inspect_message_window(), analyze_token_usage(), analyze_latency().

Add compact formatting designed for LLM consumption.

Unit-test each tool against trace fixtures.

US-6.2 - Implement target/config inspection tools

User story: As the Judge, I need to inspect the target configuration that may have caused the failure.

Acceptance criteria

Judge can inspect system/reasoning prompts, tool descriptions, retry/stop settings, and manifest rules allowed for the target.

Immutable benchmark policy/data are clearly labeled and cannot be returned as mutable settings.

Technical tasks

Implement inspect_agent_prompt(), inspect_tool_descriptions(), inspect_runtime_policy(), inspect_mutable_surface().

For tau3 later, distinguish immutable domain policy/tools from mutable ReAct-agent prompting/config.

US-6.3 - Add comparison/history tools

User story: As the Judge, I want evidence from successful cohorts and prior incidents when it helps disambiguate a failure.

Acceptance criteria

Judge can compare failed run to successful runs for the same task/tag when available.

History output contains concise outcomes, not full previous traces.

History can be disabled for controlled experiments.

Technical tasks

Implement compare_runs()/compare_to_successful_cohort().

Stub find_similar_failures() until Epic 12 persistence is ready.

Track which evidence types influenced each diagnosis.

Epic 7: Judge Ground-Truth Dataset and Failure Taxonomy

| Goal | Create independently labeled failure examples so Judge accuracy is measurable rather than anecdotal. |
| --- | --- |
| Dependencies | Epics 1, 4-6 |
| Exit milestone | A versioned labeled trace set contains real and controlled failures, with a held-out diagnosis test split for generic-vs-specialized evaluation. |

US-7.1 - Label real Target A failures

User story: As the evaluator, I need known root causes to score Judge diagnoses.

Acceptance criteria

Each labeled trace has one primary failure category, optional secondary category, evidence references, and reviewer rationale.

Labels are created independently of the Judge output.

Ambiguous cases are flagged instead of forced into a category.

Technical tasks

Review a representative sample of failed baseline traces.

Create a taxonomy grounded in Target A behavior rather than generic buzzwords.

Use a small annotation rubric so similar failures are labeled consistently.

US-7.2 - Create controlled fault-injected agent variants

User story: As the experiment owner, I need failures whose true cause is known exactly.

Acceptance criteria

Each injected variant changes one whitelisted target setting at a time.

Injection metadata records the exact intended failure cause.

Original tasks/ground truth remain unchanged.

Technical tasks

Examples: remove required tool guidance, weaken stop rule, confuse two tool descriptions, introduce excessive-retry guidance, omit a policy reminder.

Run injected variants on selected tasks and store resulting traces.

Exclude any injection where the intended failure does not actually manifest.

US-7.3 - Freeze diagnosis dev/test splits

User story: As the researcher, I need a held-out set to compare generic and specialized Judges fairly.

Acceptance criteria

Judge prompt/taxonomy tuning uses only the diagnosis dev split.

Final diagnosis metrics use the held-out split.

The split is versioned and reported.

Technical tasks

Stratify by failure type where sample size allows.

Record class imbalance and report macro metrics, not accuracy alone.

Keep UNKNOWN/ambiguous examples explicit.

Epic 8: Agent Versioning and Controlled Candidate Mutation

| Goal | Allow the Judge to propose safe, inspectable, reversible changes rather than editing a running agent in place. |
| --- | --- |
| Dependencies | Epics 4-7 |
| Exit milestone | Every candidate is an immutable child version with an explicit diff, validation, and rollback path. |

US-8.1 - Implement immutable AgentVersion records

User story: As the optimizer, I need every baseline and candidate to be reproducible.

Acceptance criteria

Version stores parent, target_id, mutable config, model/runtime settings, content hash, status, and timestamp.

Accepted/rejected versions are never overwritten.

Same configuration produces the same content hash.

Technical tasks

Create AgentVersion database model and repository.

Persist Target A baseline A0 and later tau3 baseline B0.

Store config artifacts in a diff-friendly format.

US-8.2 - Define allowed mutation operations

User story: As the system owner, I need the Judge to optimize only a safe surface.

Acceptance criteria

Allowed mutation categories are explicit per target manifest.

Candidate patch validates before evaluation.

Task-specific answers/ground truth cannot be injected into prompts.

Technical tasks

Implement operations such as edit_system_guidance, edit_reasoning_prompt, edit_tool_description_guidance, edit_retry_guidance, edit_stop_guidance.

Add length/change-size limits so the Judge cannot endlessly grow prompts.

Reject candidate changes that touch immutable benchmark configuration.

US-8.3 - Generate candidates from diagnosis

User story: As the Judge, I need to translate an evidence-backed diagnosis into one controlled hypothesis test.

Acceptance criteria

Candidate rationale links to diagnosis/evidence.

One candidate changes a small number of related settings.

Candidate can be materialized by TargetAdapter without manual editing.

Technical tasks

Create CandidateChange schema.

Implement candidate builder/validator.

Store human-readable diff for demos and review.

Epic 9: Evaluation Runner and Comparable Experiments

| Goal | Run baseline and candidate under identical conditions and return normalized metrics. |
| --- | --- |
| Dependencies | Epics 1-3, 8 |
| Exit milestone | One evaluation command can score any Target A version against a named frozen dataset split and persist per-task/aggregate metrics. |

US-9.1 - Implement Target A evaluation runner

User story: As the optimizer, I need a repeatable experiment for every candidate.

Acceptance criteria

Baseline and candidate use identical task IDs, evaluator version, model, context, temperature/seed settings, and environment snapshot.

Per-task result contains success plus efficiency metrics.

Crashes/timeouts are explicit failures, not silently dropped.

Technical tasks

Implement EvaluationAdapter.evaluate_version().

Persist task-level and aggregate results.

Support a tiny smoke split and a larger optimization split.

US-9.2 - Control stochasticity and repeated trials

User story: As the experiment owner, I need to distinguish real improvement from random variation.

Acceptance criteria

When target/user behavior is stochastic, multiple trials can be configured.

Trial seed/config is stored.

Final reports include task count and number of trials.

Technical tasks

Start deterministic where possible; add repeated trials only when needed.

Define how task-level multiple trials aggregate into success/pass@k-like metrics.

Never compare runs with different trial policies as if they were equivalent.

US-9.3 - Produce normalized metric summaries

User story: As the acceptance policy, I need consistent metrics across targets.

Acceptance criteria

Normalized result includes success, tokens, tool calls, errors/retries, latency, and target-specific extra scores.

Raw target-specific evaluator details remain available for debugging.

Technical tasks

Create EvaluationResult/AggregateMetrics models.

Define missing-metric semantics instead of substituting zero.

Add comparison helper with per-task deltas.

Epic 10: Acceptance Policy, Promotion, and Rollback

| Goal | Turn evaluation results into explicit promotion decisions; the LLM does not grade its own proposed fix. |
| --- | --- |
| Dependencies | Epic 9 |
| Exit milestone | Every candidate ends in ACCEPT/ROLLBACK/INCONCLUSIVE using auditable rules and cannot be promoted after incomplete evaluation. |

US-10.1 - Define correctness-first acceptance rules

User story: As the system owner, I need efficiency improvements to be rejected if they create unacceptable quality regressions.

Acceptance criteria

Critical regression count must be zero (or a documented target-specific tolerance).

Success must meet a configured floor relative to baseline before efficiency metrics matter.

Tokens/tool calls/latency are secondary objectives.

INCONCLUSIVE exists for insufficient/failed evaluation.

Technical tasks

Create versioned AcceptancePolicy configuration.

Start conservative: protect success first, then optimize efficiency.

Write unit tests for edge cases and conflicting metrics.

US-10.2 - Implement promote/rollback operations

User story: As the optimizer, I need safe automatic version selection.

Acceptance criteria

Accepted candidate becomes next baseline by pointer/status update, not destructive overwrite.

Rejected candidate remains queryable with reasons.

Evaluation failure can never promote a candidate.

Technical tasks

Implement decision service.

Persist reasons and metric deltas.

Add explicit rollback/revert command for demo/recovery.

Epic 11: Closed-Loop Optimizer Controller

| Goal | Connect diagnosis, mutation, evaluation, and promotion into one bounded autonomous workflow. |
| --- | --- |
| Dependencies | Epics 4-10 |
| Exit milestone | A single invocation can diagnose a Target A issue, create a candidate, evaluate it, decide ACCEPT/ROLLBACK, and optionally continue for another bounded cycle. |

US-11.1 - Implement optimizer graph/controller

User story: As the developer, I need one orchestrated workflow rather than manual scripts between stages.

Acceptance criteria

Controller can execute diagnose -> propose -> materialize -> evaluate -> compare -> decide.

State transitions are persisted/logged.

Every terminal path has a clear reason.

Technical tasks

Add optimizer graph or supervisory controller around Judge graph.

Reuse TargetAdapter/EvaluationAdapter so controller does not know target internals.

Handle failures from mutation/evaluation without corrupting baseline state.

US-11.2 - Add bounded multi-cycle optimization

User story: As the optimizer, I want to try another hypothesis after a rejected candidate without looping forever.

Acceptance criteria

Maximum candidate attempts/cycles is configurable.

Judge sees prior candidate outcome summaries.

Repeated equivalent candidates are detected/rejected.

Stop conditions include success plateau, budget exhaustion, repeated failure, and no actionable diagnosis.

Technical tasks

Add cycle_count and attempted_patch_hashes to state.

Define stopping policy.

Persist full optimization episode summary.

Epic 12: Optimization Memory and Historical Failure Retrieval

| Goal | Let future investigations learn from past diagnoses and candidate outcomes without treating history as truth. |
| --- | --- |
| Dependencies | Epics 7-11 |
| Exit milestone | Judge can retrieve relevant prior failures/fixes with outcomes; current trace evidence remains authoritative. |

US-12.1 - Persist optimization history

User story: As the system, I need structured memory of what was tried and whether it worked.

Acceptance criteria

Database links target run -> diagnosis -> candidate -> evaluation -> decision.

Accepted and rejected fixes are equally queryable.

Target ID/domain is part of every history record.

Technical tasks

Create repository methods and indexes.

Store failure tags, candidate category, measured deltas, and decision.

Add target/domain filter so airline history does not leak into unrelated target reasoning by default.

US-12.2 - Expose history as a Judge tool

User story: As the Judge, I want concise prior evidence when a similar failure occurred before.

Acceptance criteria

find_similar_failures returns summaries/outcomes, not entire traces.

Judge prompt says history is supporting evidence only.

History retrieval can be disabled in experiments.

Technical tasks

Implement tag/metadata matching first.

Add local embeddings later only if needed.

Log when memory was used so its effect can be measured.

Epic 13: Target A Experiments: Generic vs Specialized Judge + Optimizer Impact

| Goal | Produce defensible internal evidence before adding an external target. |
| --- | --- |
| Dependencies | Epics 7, 9-12 |
| Exit milestone | A reproducible report compares Judge modes and measures the closed-loop optimizer on Target A held-out tasks. |

US-13.1 - Compare generic vs target-aware Judge

User story: As the project owner, I need to test whether specialization actually improves diagnosis efficiency/quality.

Acceptance criteria

Same model, same labeled held-out traces, same model parameters, and same scoring rubric are used for both modes.

Report macro precision/recall/F1, accuracy where appropriate, UNKNOWN/fallback rate, tokens, LLM calls, diagnostic tool calls, and latency.

No claim of superiority is made if the results do not support it.

Technical tasks

Create eval_judge.py with fixed manifest/prompt versions.

Score exact/compatible failure categories with a documented mapping.

Export task-level results and aggregate table.

Perform error analysis on disagreements.

US-13.2 - Measure downstream optimization impact on Target A

User story: As the project owner, I need evidence that better diagnoses translate into better target performance.

Acceptance criteria

Compare frozen baseline A0 with final accepted version on a held-out target-task split never used for optimization.

Report success, tokens, tool calls, latency, error/retry rate, and number of accepted/rejected candidates.

Optionally compare generic-optimizer vs specialized-optimizer outcomes if budget permits.

Technical tasks

Create final Target A held-out evaluation run.

Persist all raw outputs and aggregate report.

Document negative/neutral results and any overfitting discovered.

Epic 14: Integrate tau3-bench as External Target B

| Goal | Add an independently maintained open-source ReAct target and official benchmark without changing benchmark semantics. |
| --- | --- |
| Dependencies | M4 complete; preferably Epic 13 complete |
| Exit milestone | Pinned tau3 ReAct agent runs one text domain locally, is traced in Langfuse, and produces official evaluator scores through a Tau3Adapter. |

Important: tau3 tasks include evaluation_criteria and the standard domains evaluate environment/communication according to the task reward basis. Treat the official evaluator as the external source of truth for task success; your Judge diagnoses why a run failed or was inefficient, but does not replace the official score.

US-14.1 - Pin and verify tau3-bench

User story: As the external-validation owner, I need reproducible benchmark code and data.

Acceptance criteria

Exact tau3-bench release/tag/commit is recorded; current plan targets v1.0.1 as the reproducible starting pin.

Python 3.12 environment installs tau3 core text dependencies.

tau2 check-data succeeds.

A stock smoke task can run before any optimizer integration.

Technical tasks

Add tau3 as a pinned dependency/submodule/vendor integration according to repository preference.

Record license/source and exact commit/tag in THIRD_PARTY.md.

Use text/half-duplex mode only for MVP.

Do not use the outdated original tau-bench repository/tasks.

US-14.2 - Verify local-model execution through LiteLLM

User story: As the developer, I want external validation to remain zero-cost.

Acceptance criteria

tau3 agent LLM can call an Ollama model through LiteLLM.

User simulator also uses a fixed local model/config for baseline and candidate runs.

Tool calling and simulation completion are reliable enough for a small task subset.

If local user simulation is too unstable, the limitation is documented rather than silently switching to paid APIs.

Technical tasks

Run a 1-task mock-domain spike first.

Then run 3-5 tasks in the selected real domain.

Start with low concurrency (1) on the laptop.

Record exact agent/user models, args, seed, max steps, and trial count.

tau3 uses LiteLLM and documents support for any LiteLLM provider; LiteLLM supports Ollama. Still treat local tau3 execution as an integration spike because tool-call behavior and user-simulator quality depend on the selected model.

US-14.3 - Select and freeze the first external domain

User story: As the evaluator, I need one stable tau3 domain rather than moving targets across experiments.

Acceptance criteria

Airline is the default first choice; retail is an acceptable fallback after a documented pilot.

Official domain policy, tools, database, tasks, and evaluator remain unchanged.

A fixed task split/subset is recorded for development and a disjoint held-out subset is reserved if the domain split permits it.

Benchmark version and task IDs are stored with every evaluation.

Technical tasks

Pilot airline on a small subset.

Inspect baseline success/failure mix and runtime; choose the domain before Judge-specific optimization.

Freeze task IDs and trial policy for the experiment.

Never modify task evaluation_criteria to accommodate the candidate.

US-14.4 - Use tau3 ReAct agent as the target implementation

User story: As the optimizer, I need a real external agent whose behavior I can modify without changing the benchmark world.

Acceptance criteria

Use the example ReAct pattern (THINK then ACT) rather than rewriting a new tau3 target from scratch.

Mutable surface is explicitly constrained to agent-side prompting/reasoning/runtime guidance.

Injected domain_policy and actual tool implementations remain benchmark-owned/immutable.

No task-specific hints are inserted into the agent prompts.

Technical tasks

Wrap/fork the example ReActAgent minimally so prompt/config versions are externally controllable.

Expose SYSTEM/THINK/ACT prompting and safe runtime knobs through AgentVersion.

Keep benchmark tools/policy/data read-only from optimizer mutation code.

Save the original stock ReAct agent as B0.

US-14.5 - Instrument tau3 and implement adapters

User story: As the shared optimizer, I need tau3 runs to look like any other target through internal interfaces.

Acceptance criteria

Tau3TargetAdapter creates/runs B versions and returns normalized run IDs.

Tau3EvaluationAdapter invokes official tau3 evaluation and maps RewardInfo/evaluation details to normalized metrics.

Langfuse tracing captures enough model/tool events for Judge diagnostics.

Official evaluator output remains stored verbatim alongside normalized metrics.

Technical tasks

Use tau3's optional Langfuse support where useful, or instrument the custom ReAct wrapper without changing behavior.

Map tau3 simulation/task identifiers to project run metadata.

Normalize ENV/COMMUNICATE/ACTION details without losing raw evaluator info.

Write integration tests on the mock domain before airline.

Epic 15: Cross-Target and Cross-Domain Validation

| Goal | Demonstrate that the optimizer architecture is reusable while specialization remains target/domain-specific. |
| --- | --- |
| Dependencies | Epics 13-14 |
| Exit milestone | The same Judge graph, tool contracts, versioning, evaluation normalization, and acceptance controller operate on Target A and tau3 Target B through different manifests/adapters. |

US-15.1 - Create the tau3 airline Judge manifest

User story: As the specialized Judge, I need airline-specific context without hardcoding airline logic into the graph.

Acceptance criteria

Manifest captures official tool purposes, important policy constraints, likely failure categories, relevant diagnostic tools, and allowed ReAct mutations.

Domain policy is referenced/summarized for Judge context but marked immutable.

Manifest contains no task answers or reference trajectories.

Technical tasks

Inventory airline tool schemas and policy rules from the pinned tau3 release.

Define failure taxonomy such as policy sequencing/confirmation errors, wrong tool/args, missing information, premature response, repeated/inefficient calls, and unsupported communication where supported by evidence.

Keep taxonomy broad enough to permit UNKNOWN/fallback.

US-15.2 - Run generic vs airline-specialized Judge experiment

User story: As the experiment owner, I need to test whether target/domain specialization transfers beyond my own agent.

Acceptance criteria

Both Judge modes see the same tau3 traces and use the same model settings.

Diagnosis labels come from controlled injections/manual review, not simply the tau3 pass/fail reward.

Report quality + resource usage separately from tau3 task success.

Technical tasks

Create a small labeled tau3 failure set using stock failures and safe prompt-level controlled variants.

Run both Judge modes.

Compare diagnosis metrics and token/tool-call overhead.

US-15.3 - Run closed-loop optimization on tau3 held-out tasks

User story: As the project owner, I need external evidence that Judge-generated changes can improve an agent on an independent benchmark.

Acceptance criteria

B0 baseline and final accepted Bn are evaluated on the same fixed tau3 task set and trial policy.

Official tau3 reward/evaluation results are the primary quality outcome.

Candidate changes are rejected/rolled back if official benchmark quality regresses beyond policy.

Final report clearly separates Target A results from tau3 results.

Technical tasks

Run a bounded number of optimizer cycles.

Do not optimize on final held-out task IDs.

Run final held-out evaluation once configuration is frozen.

Record accepted/rejected candidate examples.

US-15.4 - Optional second tau3 domain

User story: As the developer, I want to test domain specialization without adding a completely different benchmark framework.

Acceptance criteria

Only start after airline pipeline is stable.

Use the same ReAct implementation but a different domain manifest/evaluator data.

No core Judge graph changes are needed.

Technical tasks

Retail is the recommended second domain.

Create retail manifest, run a small generic-vs-specialized comparison, and report whether results generalize.

Treat this as a stretch goal, not a prerequisite for a strong project.

Epic 16: Reliability, Safety, and Test Coverage

| Goal | Make the optimizer trustworthy enough that failures are understandable and changes are reversible across both targets. |
| --- | --- |
| Dependencies | All core epics |
| Exit milestone | Unit/integration/end-to-end tests cover critical flows; no candidate can be promoted on incomplete evidence or broken evaluation. |

US-16.1 - Unit-test contracts and tools

User story: As a maintainer, I need failures isolated to small components.

Acceptance criteria

Manifest parsing, adapters, trace normalization, diagnostic tools, schemas, candidate validation, and acceptance logic have tests.

Most tests use fixtures and do not require live Langfuse/Ollama/tau3.

Malformed/missing telemetry is tested.

Technical tasks

Create fixtures for Target A and tau3-like traces.

Mock LLM responses for deterministic unit tests.

Test context truncation and invalid candidate patches.

US-16.2 - Integration-test both target adapters

User story: As the developer, I need confidence that the shared optimizer contracts work with real execution systems.

Acceptance criteria

Target A smoke evaluation works end-to-end.

Tau3 mock-domain integration works end-to-end.

One known good candidate can be accepted and one known bad candidate can be rolled back.

Telemetry/evaluator outage leads to INCONCLUSIVE, never ACCEPT.

Technical tasks

Create a Docker-backed/local integration profile.

Keep long local-model benchmark runs outside fast CI.

Add a pre-demo verification script.

US-16.3 - Bound unsafe/uncontrolled behavior

User story: As the system owner, I need autonomous optimization to remain constrained and reproducible.

Acceptance criteria

Target/Judge loops have step/time/model-call budgets.

Mutation tools cannot execute arbitrary shell commands or alter benchmark files.

Secrets are filtered from telemetry.

Optimizer cannot access final held-out ground truth during optimization.

Technical tasks

Separate read-only diagnostic tools from mutation tools.

Protect immutable benchmark directories/configs in code and documentation.

Add explicit target allowlists for mutable fields.

Epic 17: Developer Experience, Documentation, and Portfolio Evidence

| Goal | Make the system understandable, reproducible, and easy to explain in an interview. |
| --- | --- |
| Dependencies | Core system complete |
| Exit milestone | A clean clone can run a small demo, and the README proves what you built with real external/internal evaluation evidence. |

US-17.1 - Create reproducible commands

User story: As a reviewer, I need to run the system without learning the entire codebase first.

Acceptance criteria

Commands exist for Target A baseline, Judge diagnosis, Target A optimize loop, Judge benchmark, tau3 smoke baseline, tau3 optimize loop, and final report.

Windows/PowerShell setup is documented.

Langfuse Cloud configuration and local Ollama setup are documented.

Technical tasks

Create CLI entry points such as target-a-run, judge-run, optimize-run, eval-judge, tau3-smoke, tau3-eval.

Add sample .env and model-pull instructions.

Document expected runtimes and low-concurrency settings for the RTX 4050.

US-17.2 - Publish the technical story

User story: As a recruiter/interviewer, I need to understand exactly what is yours versus third-party infrastructure.

Acceptance criteria

README clearly labels Langfuse and tau3 responsibilities versus project-owned Judge/optimizer logic.

Architecture shows Target A and external Target B.

Generic vs specialized Judge experiment is reported with real metrics.

At least one accepted and one rejected candidate are shown.

Limitations/negative results are documented.

Technical tasks

Add architecture/loop diagrams, manifest examples, diagnosis JSON, candidate diff, evaluation tables, and limitations.

Explain why tau3 is used as independent validation rather than as the core project.

Explain why specialization is treated as an empirical hypothesis.

Do not leave placeholder performance numbers in the public README.

US-17.3 - Prepare resume/interview evidence

User story: As the candidate, I need concise claims that are supported by reproducible artifacts.

Acceptance criteria

Every numeric resume claim maps to a saved report/experiment configuration.

Project description emphasizes agentic investigation and closed-loop optimization, not merely tracing.

External tau3 result is clearly described as evaluation on an independent benchmark.

Technical tasks

Save final metrics table and experiment manifest under benchmark/reports/.

Prepare a 2-minute architecture explanation and a 5-minute deep dive.

Keep a short build-vs-buy answer explaining why Langfuse is infrastructure and why you implemented the optimization controller yourself.

# 5. Recommended Repository Structure

agent-judge-optimizer/<br>├─ pyproject.toml<br>├─ uv.lock<br>├─ .env.example<br>├─ docker-compose.dev.yml<br>├─ README.md<br>├─ configs/<br>│  ├─ targets/<br>│  │  ├─ target_a.yaml<br>│  │  └─ tau3_airline.yaml<br>│  ├─ judge/<br>│  │  ├─ generic.yaml<br>│  │  └─ specialized.yaml<br>│  └─ acceptance_policy.yaml<br>├─ src/<br>│  ├─ judge/<br>│  │  ├─ graph.py<br>│  │  ├─ state.py<br>│  │  ├─ prompts.py<br>│  │  ├─ diagnosis.py<br>│  │  └─ tool_registry.py<br>│  ├─ diagnostics/<br>│  │  ├─ trace_tools.py<br>│  │  ├─ metric_tools.py<br>│  │  ├─ comparison_tools.py<br>│  │  ├─ config_tools.py<br>│  │  └─ history_tools.py<br>│  ├─ telemetry/<br>│  │  ├─ provider.py<br>│  │  └─ langfuse_provider.py<br>│  ├─ targets/<br>│  │  ├─ base.py<br>│  │  ├─ target_a/<br>│  │  │  ├─ adapter.py<br>│  │  │  └─ evaluator.py<br>│  │  └─ tau3/<br>│  │     ├─ adapter.py<br>│  │     ├─ evaluator.py<br>│  │     ├─ react_variant.py<br>│  │     └─ instrumentation.py<br>│  ├─ optimization/<br>│  │  ├─ versions.py<br>│  │  ├─ mutations.py<br>│  │  ├─ policy.py<br>│  │  └─ controller.py<br>│  ├─ evaluation/<br>│  │  ├─ models.py<br>│  │  ├─ judge_benchmark.py<br>│  │  ├─ reports.py<br>│  │  └─ metrics.py<br>│  ├─ persistence/<br>│  │  ├─ models.py<br>│  │  ├─ repositories.py<br>│  │  └─ migrations/<br>│  └─ common/<br>│     ├─ schemas.py<br>│     ├─ config.py<br>│     └─ logging.py<br>├─ benchmark/<br>│  ├─ target_a/<br>│  │  ├─ diagnosis_labels.jsonl<br>│  │  ├─ splits.json<br>│  │  └─ reports/<br>│  ├─ tau3/<br>│  │  ├─ pinned_version.json<br>│  │  ├─ task_ids.json<br>│  │  ├─ diagnosis_labels.jsonl<br>│  │  └─ reports/<br>│  └─ final/<br>├─ scripts/<br>│  ├─ baseline_target_a.py<br>│  ├─ judge_run.py<br>│  ├─ optimize_run.py<br>│  ├─ eval_judge.py<br>│  ├─ tau3_smoke.py<br>│  └─ final_eval.py<br>└─ tests/<br>   ├─ unit/<br>   ├─ integration/<br>   └─ fixtures/

# 6. Target Manifest Contract

The manifest is the core of the specialization experiment. The Judge graph stays shared; the manifest changes the domain knowledge, relevant failure categories, available diagnostic tools, allowed mutations, and optimization priorities.

target_id: tau3_airline_react<br>adapter: tau3<br>benchmark:<br>  framework: tau3-bench<br>  pinned_version: v1.0.1<br>  domain: airline<br>  evaluator: official_tau3<br>  immutable:<br>    - domain_policy<br>    - domain_tools<br>    - domain_database<br>    - tasks<br>    - evaluation_criteria<br><br>agent:<br>  implementation: react_agent<br>  mutable_surface:<br>    - system_wrapper_guidance<br>    - think_prompt<br>    - act_prompt<br>    - retry_guidance<br>    - stop_guidance<br><br>judge_context:<br>  tool_catalog: <normalized from pinned domain><br>  behavioral_rules:<br>    - "Follow the benchmark domain policy."<br>    - "Do not invent task-specific facts or bypass required user interaction."<br>  failure_taxonomy:<br>    - wrong_tool_selection<br>    - invalid_tool_arguments<br>    - policy_sequence_error<br>    - missing_required_information<br>    - repeated_or_inefficient_tool_use<br>    - premature_response<br>    - unsupported_or_incomplete_communication<br>    - unknown<br>  judge_tools:<br>    - get_trace_summary<br>    - list_tool_calls<br>    - inspect_tool_call<br>    - inspect_message_window<br>    - inspect_agent_prompt<br>    - analyze_token_usage<br>    - compare_runs<br>    - find_similar_failures<br><br>optimization_priorities:<br>  task_success: 1.0<br>  critical_policy_regression: hard_constraint<br>  tokens: 0.30<br>  tool_calls: 0.30<br>  latency: 0.15

Create a separate Target A manifest from the real agent you already built. Do not copy the tau3 taxonomy into Target A unless the failure modes actually apply.

# 7. Minimum Persistent Data Model

| Entity | Purpose | Key fields |
| --- | --- | --- |
| target_profiles | Versioned target/manifest definitions. | target_id, adapter_type, manifest_version, domain, mutable_surface_json, created_at |
| agent_versions | Immutable target configurations. | id, target_id, parent_id, prompt/config_json, model_config_json, content_hash, status, created_at |
| target_runs | Index executions and correlate Langfuse trace IDs. | run_id, target_id, trace_id, task_id, agent_version_id, benchmark_version, model_id, status, created_at |
| judge_runs | Track Judge investigations. | id, target_run_id, manifest_version, mode, model_id, diagnosis_id, tokens, tool_calls, latency, fallback_used |
| diagnoses | Structured root-cause result. | id, failure_type, root_cause, severity, confidence, evidence_json, recommended_change_type |
| candidate_changes | Versioned proposed optimization. | id, diagnosis_id, parent_version_id, candidate_version_id, change_type, patch_json, rationale |
| evaluation_runs | One benchmark execution of one agent version. | id, target_id, agent_version_id, benchmark_version, split, trials, started_at, completed_at, aggregate_metrics_json |
| evaluation_items | Per-task/trial result. | evaluation_run_id, task_id, trial, success, tokens, tool_calls, latency_ms, errors_json, target_specific_scores_json |
| optimization_decisions | Promotion history. | id, target_id, baseline_version_id, candidate_version_id, policy_version, decision, reasons_json, created_at |
| failure_labels | Independent Judge ground truth. | trace/run_id, target_id, primary_label, secondary_labels_json, evidence_json, source(real/injected/manual), split |

# 8. Practical Build Sequence

This is sequencing, not a deadline. Advance when exit criteria are met. The external tau3 track intentionally starts late so it validates a working optimizer rather than becoming an infrastructure distraction.

| Stage | Primary work | Exit criteria |
| --- | --- | --- |
| 1 | Epic 0 + Epic 1 audit | Environment works; Target A baseline/config/benchmark splits are frozen. |
| 2 | Epic 2 + Epic 3 | Target A traces are complete; TraceProvider and TargetAAdapter/EvaluationAdapter work. |
| 3 | Epics 4-6 | Judge autonomously selects diagnostic tools and emits evidence-backed structured diagnoses. |
| 4 | Epic 7 | Independent labeled failure set exists with dev/held-out diagnosis splits. |
| 5 | Epics 8-10 | Immutable candidate creation, comparable evaluation, and deterministic accept/rollback work. |
| 6 | Epics 11-12 | Full bounded closed loop + optimization memory works on Target A. |
| 7 | Epic 13 | Generic-vs-specialized Judge report + Target A held-out before/after metrics are complete. |
| 8 | Epic 14 | Pinned tau3 environment, local models, ReAct target, Langfuse instrumentation, and official evaluator integration work. |
| 9 | Epic 15 | Cross-target optimizer + tau3 external results are complete; optional retail extension if useful. |
| 10 | Epics 16-17 | Reliability pass, documentation, final reports, demo, and resume evidence. |

# 9. Exactly What to Implement Next

## Day 1 - Convert the existing target into a frozen system-under-test

Create Target A inventory: current model, prompts, tools, tool schemas/descriptions, retry/stop behavior, data dependencies, and evaluator.

Create AgentVersion A0 containing the exact current mutable configuration and a content hash.

Freeze benchmark version/snapshot and choose development versus held-out task IDs before optimization.

Run a clean baseline and save per-task metrics. Do not change the agent yet.

Move the project environment to Python 3.12 if it is not already there, so later tau3 integration does not require a disruptive runtime migration.

## Day 2 - Finish observability and normalized trace access

Instrument Target A with Langfuse Cloud Hobby.

Verify successful and failed runs include task_id, target_id, agent_version_id, model configuration, tool calls, timing, and available token metadata.

Implement TraceProvider plus LangfuseTraceProvider.get_trace_summary() and list_tool_calls().

Save two or three trace fixtures for unit tests.

Do not write the Judge prompt until you can inspect real normalized traces.

## Day 3 - Implement the first real Judge investigation

Create JudgeGraphState and Diagnosis schema.

Implement three diagnostic tools: get_trace_summary, list_tool_calls, inspect_tool_call.

Build the smallest LangGraph loop where the Judge chooses which tool to call and then returns a structured diagnosis.

Run it against one known Target A failure and manually check whether evidence references are valid.

Add budgets before adding more tools.

## First tau3 work - only after Target A closed loop is stable

Pin tau3-bench v1.0.1 (or another exact chosen commit/tag after rechecking release notes) and run tau2 check-data.

Verify a mock-domain run with Ollama through LiteLLM.

Run 3-5 airline tasks with the stock/example ReAct agent and a fixed local user simulator.

Capture official evaluator output and Langfuse traces.

Only then write Tau3TargetAdapter/Tau3EvaluationAdapter and the airline Judge manifest.

# 10. Engineering Gates Before Moving to the Next Layer

| Gate | Must be true before continuing |
| --- | --- |
| Target A baseline gate | A0 and dataset/evaluator versions are frozen; held-out task IDs are selected; baseline can be rerun. |
| Telemetry gate | A run can be reconstructed sufficiently from TraceProvider; task/target/version IDs are never missing. |
| Judge gate | Judge selects different diagnostic tools on different failures and outputs schema-valid evidence-backed diagnoses. |
| Specialization gate | Changing only the manifest changes failure taxonomy/tool availability; Judge graph source code remains unchanged. |
| Diagnosis benchmark gate | Labels come from manual/controlled known causes, not the Judge itself. |
| Mutation gate | All target changes produce a new immutable version; no in-place mutation. |
| Evaluation gate | Baseline/candidate use the same benchmark snapshot, model/user settings, seeds/trials, and evaluator. |
| Promotion gate | Incomplete/crashed evaluation can never promote a candidate. |
| Target A evidence gate | Generic-vs-specialized and held-out before/after results exist before tau3 integration. |
| tau3 installation gate | Pinned version, Python 3.12 environment, data check, and stock smoke run all succeed. |
| tau3 fairness gate | Official tasks/policy/tools/database/evaluator are unchanged; mutable agent surface is documented. |
| Cross-target gate | Same optimizer controller runs Target A and tau3 through adapters without target-specific branches in core Judge logic. |

# 11. Metrics to Capture From the Beginning

| Layer | Metric | Why it matters |
| --- | --- | --- |
| Target | Task success / official benchmark reward | Primary quality outcome. |
| Target | Input/output/total tokens per task | Inference efficiency. |
| Target | Tool calls per task | Trajectory efficiency. |
| Target | Tool error/retry count | Operational robustness. |
| Target | Latency per task | Performance/cost proxy for local inference. |
| Judge | Diagnosis accuracy + macro precision/recall/F1 | Core Judge quality on labeled failures. |
| Judge | UNKNOWN/fallback rate | Shows where specialization is insufficient. |
| Judge | Input/output tokens per diagnosis | Tests whether specialization reduces inference overhead. |
| Judge | Diagnostic tool calls per diagnosis | Measures investigation complexity. |
| Judge | LLM calls + latency | Measures practical Judge overhead. |
| Optimizer | Accepted/rejected candidate count | Shows whether the controller is selective. |
| Optimizer | Cycles to accepted improvement | Measures optimization efficiency. |
| Optimizer | Critical regressions introduced/rejected | Demonstrates correctness-first safety. |
| Cross-target | Same-core-code coverage | Evidence that reuse comes from adapters/manifests, not duplicated optimizer logic. |
| tau3 | Official ENV/COMMUNICATE/ACTION details where applicable | External evaluator evidence beyond your own metrics. |

# 12. Risk Register and Mitigations

| Risk | Why it happens | Mitigation |
| --- | --- | --- |
| Local model is weak at tool use | 4B/8B models are weaker than premium hosted models. | Use narrow tools, structured outputs, low temperature, small budgets; use 8B for serious Judge runs. |
| Specialized Judge overfits known failures | Narrow taxonomy can create tunnel vision. | Keep UNKNOWN + general fallback; use held-out failure labels and novel/injected failure cases. |
| Judge context grows too large | Agent traces can exceed practical 6 GB VRAM context. | Retrieve evidence through diagnostic tools; summarize/truncate outputs; never paste full traces by default. |
| Optimizer improves efficiency but hurts quality | Shorter paths can remove necessary behavior. | Correctness/critical-regression constraints come before token/tool/latency objectives. |
| Target A benchmark bias | You control Target A and its evaluator. | Freeze held-out tasks early and add tau3 as independent external validation. |
| tau3 local user simulator is unstable | Small local models may not simulate users faithfully. | Use fixed model/settings, low concurrency, repeated trials where needed; document limitation; do not silently use paid APIs. |
| tau3 evaluator drift across versions | The benchmark has received task/grading fixes. | Pin exact version/commit and record task IDs/evaluator version with results. |
| Benchmark leakage through mutation | Judge could inject task-specific hints into prompts. | Mutation validator forbids task IDs, gold actions/answers, and benchmark-file edits. |
| Langfuse coupling | Direct SDK calls spread into Judge code. | TraceProvider + normalized internal schemas. |
| Target coupling | Optimizer accumulates if/else branches for each agent. | TargetAdapter/EvaluationAdapter + manifest-specific configuration. |
| Optimization loop never stops | Rejected candidates can trigger endless retries. | Max cycles, duplicate-patch hashes, budget exhaustion, no-actionable-diagnosis terminal state. |
| Results are not statistically meaningful | Small task sets and stochastic LLM/user behavior. | Report task/trial counts, confidence/variance where possible, and avoid overclaiming from tiny samples. |
| Hardware pressure | RTX 4050 has 6 GB VRAM. | Run target/Judge sequentially; 4B for iteration, 8B for final Judge runs; low tau3 concurrency; Cloud Langfuse. |

# 13. Definition of Done

Target A is treated as an immutable baseline plus versioned candidates; its dev and held-out task splits are frozen before optimization.

Langfuse traces Target A and Judge runs with stable target/task/version/model identifiers.

Judge is a real tool-using LangGraph agent that chooses diagnostic tools and follows different investigation paths.

Target manifests configure specialized failure taxonomy, domain rules, Judge tool availability, allowed mutations, and optimization priorities.

Generic Judge mode and target-aware Judge mode use the same underlying model and can be compared fairly.

An independently labeled failure dataset exists with real and controlled known failures plus a held-out diagnosis split.

Judge can generate a controlled immutable target-agent candidate linked to diagnosis evidence.

Evaluation runner compares baseline and candidate on the same frozen workload.

Acceptance policy automatically ACCEPTS, ROLLS BACK, or marks INCONCLUSIVE with explicit reasons and cannot promote incomplete evaluation.

At least one full Target A optimization episode demonstrates real before/after metrics and at least one rejected candidate.

Generic-vs-specialized Judge experiment reports diagnosis quality and resource usage without assuming the specialized Judge wins.

tau3-bench is pinned to an exact release/commit and can run a local-model smoke evaluation.

The tau3 example ReAct agent is integrated as Target B without changing official domain policy, tools, database, tasks, or evaluator.

Tau3 official evaluator output is preserved and used as the primary external task-success signal.

The same Judge/optimizer core works with Target A and Target B through adapters/manifests.

At least one tau3 external before/after experiment is reproducible; final report states whether improvement occurred, including neutral/negative results if applicable.

Repository documentation clearly separates third-party infrastructure from your Judge/optimizer contribution and contains no placeholder metrics.

# 14. Current Technical References Used for This Revision

These sources were rechecked while revising the plan. Pin versions in the repository because APIs and benchmark grading can change.

tau3-bench repository / current README: https://github.com/sierra-research/tau2-bench

tau3 agent developer guide: https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/agent/README.md

tau3 runnable ReAct example: https://github.com/sierra-research/tau2-bench/blob/main/examples/agents/react_agent.py

tau3 domain structure and task/evaluation schema: https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/domains/README.md

tau3 evaluator implementation: https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/evaluator/evaluator.py

tau3 CLI reference: https://github.com/sierra-research/tau2-bench/blob/main/docs/cli-reference.md

tau3 release notes / v1.0.1 grading notes: https://github.com/sierra-research/tau2-bench/blob/main/RELEASE_NOTES.md

LiteLLM providers including Ollama: https://docs.litellm.ai/docs/

LangGraph overview/reference: https://reference.langchain.com/python/langgraph/overview

Langfuse LangGraph/LangChain integration: https://langfuse.com/integrations/frameworks/langgraph

Langfuse observability: https://langfuse.com/docs/observability/get-started

Ollama tool calling: https://docs.ollama.com/capabilities/tool-calling

Ollama context length: https://docs.ollama.com/context-length

# Appendix A. Implementation Task Tracker

| Done | Epic | Task | Owner / Notes | Evidence / PR |
| --- | --- | --- | --- | --- |
| ☐ | 0 | Repo / Python 3.12 / env baseline |  |  |
| ☐ | 0 | Ollama tool + structured-output smoke tests |  |  |
| ☐ | 0 | Postgres + migrations |  |  |
| ☐ | 1 | Target A inventory + mutable-surface map |  |  |
| ☐ | 1 | Freeze AgentVersion A0 |  |  |
| ☐ | 1 | Freeze dev/held-out benchmark split |  |  |
| ☐ | 1 | Collect Target A baseline |  |  |
| ☐ | 2 | Langfuse tracing for Target A |  |  |
| ☐ | 2 | TraceProvider abstraction |  |  |
| ☐ | 2 | Judge tracing/metadata |  |  |
| ☐ | 3 | Normalized telemetry schemas |  |  |
| ☐ | 3 | TargetAdapter/EvaluationAdapter interfaces |  |  |
| ☐ | 3 | TargetAAdapter + evaluator |  |  |
| ☐ | 3 | JudgeGraphState |  |  |
| ☐ | 4 | Judge investigation graph |  |  |
| ☐ | 4 | Diagnosis schema/confidence |  |  |
| ☐ | 4 | Budgets/context controls |  |  |
| ☐ | 5 | Target manifest schema |  |  |
| ☐ | 5 | Generic Judge mode |  |  |
| ☐ | 5 | Target A specialized Judge mode |  |  |
| ☐ | 5 | Fallback routing |  |  |
| ☐ | 6 | Trace diagnostic tools |  |  |
| ☐ | 6 | Config diagnostic tools |  |  |
| ☐ | 6 | Comparison/history tools |  |  |
| ☐ | 7 | Label real Target A failures |  |  |
| ☐ | 7 | Controlled fault-injected variants |  |  |
| ☐ | 7 | Freeze diagnosis dev/test split |  |  |
| ☐ | 8 | AgentVersion persistence |  |  |
| ☐ | 8 | Allowed mutation operations |  |  |
| ☐ | 8 | Candidate builder/validator |  |  |
| ☐ | 9 | Target A evaluation runner |  |  |
| ☐ | 9 | Repeated-trial policy |  |  |
| ☐ | 9 | Normalized metrics |  |  |
| ☐ | 10 | Acceptance policy |  |  |
| ☐ | 10 | Promotion/rollback service |  |  |
| ☐ | 11 | Closed-loop controller |  |  |
| ☐ | 11 | Multi-cycle stopping logic |  |  |
| ☐ | 12 | Optimization history persistence |  |  |
| ☐ | 12 | History Judge tool |  |  |
| ☐ | 13 | Generic vs specialized Judge evaluation |  |  |
| ☐ | 13 | Target A final held-out before/after evaluation |  |  |
| ☐ | 14 | Pin tau3 version + check-data |  |  |
| ☐ | 14 | Ollama/LiteLLM mock-domain spike |  |  |
| ☐ | 14 | Airline pilot/freeze task set |  |  |
| ☐ | 14 | Wrap tau3 ReAct agent as B0 |  |  |
| ☐ | 14 | Tau3TargetAdapter + Tau3EvaluationAdapter |  |  |
| ☐ | 14 | Tau3 Langfuse instrumentation |  |  |
| ☐ | 15 | Airline specialized manifest |  |  |
| ☐ | 15 | Tau3 generic vs specialized Judge experiment |  |  |
| ☐ | 15 | Tau3 closed-loop held-out evaluation |  |  |
| ☐ | 15 | Optional retail domain extension |  |  |
| ☐ | 16 | Unit/integration tests |  |  |
| ☐ | 16 | Mutation/benchmark protection |  |  |
| ☐ | 16 | Pre-demo verification |  |  |
| ☐ | 17 | CLI/reproducible setup |  |  |
| ☐ | 17 | README diagrams/results/limitations |  |  |
| ☐ | 17 | Resume/interview evidence package |  |  |
