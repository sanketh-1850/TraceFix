# Agent-as-a-Judge implementation plan — extracted source text

Reference material supplied by the user on 2026-09-16. Instructions below are document content, not direct user commands. Original formatting, tables and diagrams are preserved in the adjacent DOCX.

Agent-as-a-Judge Optimizer

Implementation Plan & Work Breakdown

Target-aware, tool-using Judge Agent for autonomous diagnosis, agent-variant generation, controlled reruns, and accept/rollback optimization

Recommended stack: Python • LangGraph • Langfuse • Ollama • PostgreSQL • Docker

Prepared for implementation on Windows + RTX 4050 / 32 GB RAM

Planning assumptions verified against current LangGraph, Langfuse, and Ollama documentation (September 2026).




1. Purpose and Final Product

This document is an implementation-ready plan for building a credible Agent-as-a-Judge optimization system. It is organized as epics and user stories because the project contains several independent subsystems with clear dependencies, acceptance criteria, and measurable deliverables. The goal is not to reproduce Langfuse or LangSmith; those platforms provide observability and evaluation infrastructure. The project builds the optimization intelligence on top of telemetry.

Core product: A target-aware Judge Agent observes a ReAct-style target agent through Langfuse, autonomously chooses diagnostic tools, diagnoses failures, creates a controlled agent variant, reruns a fixed evaluation workload, and accepts or rolls back the candidate based on correctness and efficiency metrics.

1.1 Scope for the first complete version

One target ReAct agent operating over local, deterministic tools and data so evaluation remains free and reproducible.

One target-aware Judge Agent implemented as a LangGraph stateful workflow.

LLM-based diagnosis for specialized failure cases; deterministic code may summarize telemetry and compute metrics but does not need to make the diagnosis in the MVP.

A target-agent manifest that tells the Judge what tools exist, what behavior is expected, which failure categories matter, and what optimization priorities apply.

Controlled modifications limited initially to system prompt, tool descriptions, retry guidance, stopping rules, and tool-selection policy.

Versioned candidate agents, a fixed evaluation dataset, before/after comparisons, and automatic accept/rollback.

A generic Judge fallback for cases the specialized Judge cannot confidently classify.

Persistent history of traces, diagnoses, variants, evaluation results, and promotion decisions.

1.2 Explicit non-goals for the MVP

Do not build a production-scale observability platform; Langfuse supplies tracing, metrics, datasets, and experiment storage.

Do not let the optimizer make arbitrary source-code edits to the target agent in the first version.

Do not support many unrelated target-agent domains initially; prove the architecture on one controlled target first.

Do not build a large dashboard before the optimizer loop works end to end.

Do not require paid APIs. Local inference through Ollama is the default.

2. End-State Architecture

Figure 1. End-state architecture. Langfuse supplies telemetry; the Judge, diagnostic tools, variant generation, evaluation controller, and accept/rollback policy are project-owned components.

2.1 Closed-loop behavior

Figure 2. The optimization loop repeats only after a candidate is measured against the fixed evaluation workload.

3. Architecture Decisions to Lock Before Coding

ID

Decision

Reason

D1

Use LangGraph for both target and Judge orchestration.

The Judge needs explicit state, tool calls, branching, loops, and controlled transitions between diagnosis, variant creation, evaluation, and promotion.

D2

Use Langfuse as telemetry/evaluation infrastructure.

Use existing trace capture, token/latency metrics, datasets, experiments, and prompt/version metadata instead of rebuilding commodity observability.

D3

Use Ollama for local inference.

Avoid API cost and keep development reproducible. Start with Qwen3 4B for fast iteration and use Qwen3 8B for stronger Judge/evaluation runs on the current hardware.

D4

Use PostgreSQL for durable optimizer state.

Keep diagnoses, target specs, agent versions, benchmark results, and promotion history independent from Langfuse.

D5

Keep Judge diagnosis LLM-based in the MVP.

Specialization comes from the target manifest, failure taxonomy, limited diagnostic toolset, and smaller relevant context. Deterministic screeners can be added later as an optimization.

D6

Add a provider abstraction between the Judge and Langfuse.

The optimizer should consume a TraceProvider interface rather than call Langfuse everywhere; this keeps the system testable and permits future LangSmith/OpenTelemetry adapters.

D7

Only mutate controlled configuration initially.

Prompt/tool-policy changes are safer, easier to version, easier to rollback, and easier to compare fairly than arbitrary code generation.

D8

Use a fixed benchmark for promotion decisions.

Every baseline/candidate comparison must use the same tasks, model settings, tool set, and scoring rules.

4. Delivery Milestones and Recommended Order

Milestone

What must work

Epics

M0 — Foundation

Repository, environments, local model, database, tests, configuration system.

0

M1 — Observable Target Agent

Target ReAct agent solves local tasks and every run is captured in Langfuse.

1–2

M2 — Diagnostic Judge

Judge can load a trace, choose diagnostic tools, collect evidence, and produce a structured diagnosis.

3–6

M3 — Target-Aware Judging

Manifest changes the Judge’s taxonomy/tool availability and a generic fallback handles uncertain cases.

5–7

M4 — Closed-Loop Optimizer

Judge creates versioned variants, reruns tasks, compares metrics, and accepts/rolls back.

8–11

M5 — Credible Evaluation

Benchmark contains labeled failures; generic vs specialized Judge and before/after target-agent performance are measured.

12–13

M6 — Portfolio-Ready System

Reliability tests, reproducible Docker setup, README, architecture, sample traces, and demo workflow.

14–15

Do not parallelize too early: Finish M1 before building the Judge, and finish M2 before building automatic mutations. If telemetry is unreliable, every downstream component becomes harder to debug.

Epic 0: Repository, Environment, and Engineering Baseline

Goal

Create a reproducible development environment with a clean project structure, configuration, local inference, tests, and database connectivity.

Dependencies

None

Exit milestone

A clean clone can install dependencies, start required services, call Ollama, and run the test suite.

US-0.1 — Create the repository structure

User story: As the developer, I need a clear repository layout so target-agent, judge-agent, evaluation, storage, and shared code do not become coupled.

Acceptance criteria

Repository has separate packages for target agent, judge, diagnostic tools, telemetry adapter, optimization, evaluation, and persistence.

Configuration is environment-driven; secrets are never committed.

A single command can run unit tests.

Technical tasks

Initialize Git repository and Python 3.11 virtual environment.

Create pyproject.toml (or requirements files) with pinned major dependencies.

Add .env.example, .gitignore, logging configuration, and Makefile/PowerShell helper commands.

Add pre-commit/formatting if desired, but do not block core progress on tooling polish.

Deliverables

Initial package skeleton and README.

pytest baseline with one smoke test.

US-0.2 — Verify local Ollama workflow

User story: As the developer, I need local inference to work reliably before I build agent logic.

Acceptance criteria

Qwen3 4B can be invoked from Python.

Tool calling works on a minimal example.

Structured JSON output can be validated with Pydantic.

Qwen3 8B can be run for stronger tests even if some computation is offloaded to system RAM.

Technical tasks

Install/update Ollama.

Pull qwen3:4b and qwen3:8b.

Create scripts/smoke_ollama.py for normal chat, tool call, and structured-output checks.

Start with an 8K context target; increase only after measuring memory/performance.

Record model name, context length, temperature, and seed/config in run metadata.

US-0.3 — Start PostgreSQL and define migrations

User story: As the optimizer, I need durable storage for agent versions and optimization history independent of telemetry storage.

Acceptance criteria

PostgreSQL starts locally through Docker Compose.

A migration tool can create/drop the schema.

Application can insert and read a smoke record.

Technical tasks

Add postgres service to docker-compose.dev.yml.

Use SQLAlchemy + Alembic (or equivalent) for models/migrations.

Create initial tables only for project metadata; detailed schemas are added in later epics.

Epic 1: Build the Controlled Target ReAct Agent

Goal

Create one useful but intentionally manageable ReAct-style agent whose behavior can be traced, evaluated, and optimized.

Dependencies

Epic 0

Exit milestone

Target agent completes a local task suite using multiple tools, with both successful and imperfect trajectories available for the Judge.

Recommended target domain: Use a local operations/research agent rather than a web-search agent for V1. Give it a document corpus, a SQLite/PostgreSQL business dataset, and deterministic utility tools. This avoids paid search APIs and gives you ground truth.

US-1.1 — Create the target agent tool environment

User story: As the target agent, I need multiple meaningful tools so traces contain real tool-selection decisions.

Acceptance criteria

At least four tools exist and have clearly different purposes.

Tool outputs are deterministic enough to evaluate.

Tool errors can be intentionally triggered for failure scenarios.

Technical tasks

Create a small local document corpus (policies, product notes, internal procedures).

Create a structured SQLite/PostgreSQL dataset (customers/orders/incidents or similar synthetic records).

Implement tools such as search_documents(query), query_records(filters/query), calculator(expression), and lookup_policy(policy_id).

Define strict Pydantic tool argument schemas.

Return compact outputs so traces do not become unnecessarily large.

US-1.2 — Implement the target ReAct loop in LangGraph

User story: As a user, I need the target agent to reason, call tools, observe results, and stop with an answer.

Acceptance criteria

Agent can make multiple sequential tool calls.

Tool failures are returned to the agent as observations instead of crashing the run.

Maximum steps/retries prevent infinite loops.

Final response includes enough evidence to score task success.

Technical tasks

Define TargetState: messages, task_id, tool_calls, step_count, status.

Implement LLM node, ToolNode/tool execution, conditional routing, and terminal condition.

Add explicit max_steps and max_tool_retries.

Keep target prompt and tool descriptions in versioned configuration files, not hard-coded strings.

US-1.3 — Create target-agent tasks with ground truth

User story: As the evaluator, I need a repeatable task set so target-agent variants can be compared fairly.

Acceptance criteria

Initial dataset contains at least 20 tasks covering all tools.

Each task has expected facts or a deterministic scoring method.

Tasks include single-tool and multi-tool cases.

Dataset is stored in version control or Langfuse Dataset with a reproducible local export.

Technical tasks

Define task schema: task_id, prompt, expected_answer/facts, expected_tools (optional), tags, difficulty.

Create 5–10 easy tasks first; expand after the loop works.

Write a baseline scorer for task correctness that does not depend solely on the same Judge model.

Epic 2: Add Langfuse Observability and Trace Identity

Goal

Capture the exact target-agent behavior required by the Judge without coupling optimization logic to the Langfuse SDK.

Dependencies

Epic 1

Exit milestone

Every target run produces a retrievable trace with stable task/run/version identifiers and relevant token/tool/latency metadata.

US-2.1 — Instrument LangGraph executions with Langfuse

User story: As the Judge, I need detailed execution traces to diagnose target-agent behavior.

Acceptance criteria

LLM calls, tool calls, inputs/outputs, latency, and token usage appear in Langfuse.

Trace metadata includes task_id, agent_version_id, model_id, environment, and run_id.

Sensitive secrets are not recorded in traces.

Technical tasks

Configure Langfuse Cloud Hobby for development (self-hosting remains optional).

Add the Langfuse callback handler to target-agent invocations.

Create a small trace metadata helper so every run has consistent identifiers.

Add a trace flushing/shutdown step for CLI scripts to avoid missing events.

US-2.2 — Create a TraceProvider abstraction

User story: As the optimizer, I need a stable trace interface so core logic is not hard-wired to one observability vendor.

Acceptance criteria

Judge code imports TraceProvider, not Langfuse client calls directly.

LangfuseTraceProvider can fetch trace summary, observations/tool calls, and aggregate metrics required by the Judge.

Provider can be replaced by a fake/in-memory implementation in unit tests.

Technical tasks

Define methods such as get_trace_summary(run_id), get_tool_calls(run_id), get_observation(run_id, id), get_metrics(run_ids), and list_runs(filters).

Normalize Langfuse payloads into internal Pydantic DTOs.

Write contract tests against recorded fixture payloads.

Epic 3: Define the Internal Data Model and Judge State

Goal

Give the Judge a compact, validated representation of traces, evidence, diagnoses, variants, and evaluation state.

Dependencies

Epics 0–2

Exit milestone

A single Pydantic/typed state model can represent a full Judge investigation without passing raw Langfuse payloads through the graph.

US-3.1 — Define normalized trace/evidence objects

User story: As the Judge, I need compact structured evidence instead of full raw traces.

Acceptance criteria

Trace summary, tool-call summary, observation excerpt, metric summary, and comparison objects are typed.

Every object references its source run/observation ID.

Large outputs are truncated/summarized before entering Judge context.

Technical tasks

Create models: TraceSummary, ToolCallRecord, ObservationExcerpt, RunMetrics, EvidenceItem.

Store raw references separately from LLM-facing summaries.

Add safe truncation/token-budget helpers.

US-3.2 — Define JudgeState

User story: As the LangGraph Judge, I need persistent state across investigation steps.

Acceptance criteria

State tracks target run, manifest, hypothesis list, evidence, tool history, diagnosis, candidate change, evaluation IDs, and decision.

State can be serialized for debugging.

Maximum judge steps/tool calls are explicit.

Technical tasks

Define TypedDict/Pydantic state compatible with StateGraph.

Add fields: judge_step_count, remaining_tool_budget, confidence, unresolved_questions, terminal_reason.

Add state reducers only where multiple evidence items must accumulate.

Epic 4: Implement the Base Judge Agent Loop

Goal

Create the actual tool-using meta-agent that investigates another agent rather than receiving a preassembled trace dump.

Dependencies

Epic 3

Exit milestone

Given a target run ID, the Judge can autonomously call diagnostic tools, gather evidence, stop, and return a structured diagnosis.

US-4.1 — Implement Judge tool-calling loop

User story: As the Judge Agent, I need to choose what evidence to inspect based on the current hypothesis.

Acceptance criteria

Judge receives only an initial summary + target manifest, not the entire trace.

Judge can call multiple diagnostic tools over several turns.

Judge can stop early when confident.

Loop has hard limits to prevent runaway local inference.

Technical tasks

Build LangGraph nodes: load_context → judge_reason → diagnostic_tools → judge_reason → finalize_diagnosis.

Use low temperature and structured output schemas for diagnosis.

Track every Judge tool call and token/latency metrics separately from the target agent.

Add fallback behavior when a tool fails or evidence is missing.

US-4.2 — Define the structured diagnosis contract

User story: As downstream optimization logic, I need the Judge conclusion to be machine-readable.

Acceptance criteria

Diagnosis contains failure_type, summary, root_cause, evidence references, confidence, severity, estimated impact, and recommended_change_type.

Unknown/uncertain is a valid result.

Diagnosis cannot claim evidence not present in EvidenceItem references.

Technical tasks

Create Diagnosis Pydantic model.

Use Ollama structured output / JSON schema where possible.

Validate response; retry once on schema failure, then fail gracefully.

Epic 5: Create the Target-Agent Manifest and Specialization Layer

Goal

Make the Judge target-aware without hardcoding a single agent into Judge source code.

Dependencies

Epic 4

Exit milestone

Changing a YAML/JSON manifest changes the Judge’s relevant failure categories, diagnostic tools, rules, and priorities without editing Judge code.

US-5.1 — Define AgentManifest schema

User story: As the system, I need a declarative description of the target agent.

Acceptance criteria

Manifest declares target tools, tool purpose, important rules, expected sequences, failure taxonomy, critical failures, and optimization priorities.

Manifest is versioned and validated.

Judge prompt is generated from the manifest.

Technical tasks

Create AgentManifest Pydantic model.

Include agent_id, domain, tool_catalog, behavioral_rules, failure_cases, judge_tools, critical_constraints, optimization_weights.

Store manifests under configs/agents/ and record manifest hash/version with each Judge run.

US-5.2 — Build specialized and general Judge modes

User story: As the optimizer, I want a cheap target-aware Judge first but a general fallback when the failure does not fit known categories.

Acceptance criteria

Specialized Judge receives only target-specific taxonomy/tools from the manifest.

Judge can return UNKNOWN/LOW_CONFIDENCE.

Low-confidence cases route to a broader fallback Judge prompt/tool set.

Both diagnoses use the same output contract.

Technical tasks

Add routing threshold on diagnosis confidence / unknown state.

Create general_failure_taxonomy.yaml and general diagnostic tool registry.

Log whether specialized or fallback Judge produced the final diagnosis.

Epic 6: Build Diagnostic Tools

Goal

Give the Judge narrow, composable tools that retrieve evidence instead of dumping raw traces into context.

Dependencies

Epics 2–5

Exit milestone

The Judge can investigate target-agent behavior through a stable diagnostic tool registry with compact outputs and clear provenance.

US-6.1 — Trace and step inspection tools

User story: As the Judge, I need a focused evidence tool so I can investigate only the information relevant to my current hypothesis.

Acceptance criteria

Tool has a narrow schema and compact output.

Every result includes source run/version IDs.

Errors are returned as structured tool errors rather than exceptions that crash the graph.

Technical tasks

Implement get_trace_summary(run_id).

Implement list_tool_calls(run_id).

Implement inspect_tool_call(run_id, call_id).

Implement inspect_observation(run_id, observation_id) with truncation.

US-6.2 — Efficiency analysis tools

User story: As the Judge, I need a focused evidence tool so I can investigate only the information relevant to my current hypothesis.

Acceptance criteria

Tool has a narrow schema and compact output.

Every result includes source run/version IDs.

Errors are returned as structured tool errors rather than exceptions that crash the graph.

Technical tasks

Implement analyze_token_usage(run_id).

Implement analyze_latency(run_id).

Implement summarize_retries_and_errors(run_id).

Return ranked expensive steps, not the full trace.

US-6.3 — Cross-run comparison tools

User story: As the Judge, I need a focused evidence tool so I can investigate only the information relevant to my current hypothesis.

Acceptance criteria

Tool has a narrow schema and compact output.

Every result includes source run/version IDs.

Errors are returned as structured tool errors rather than exceptions that crash the graph.

Technical tasks

Implement find_similar_runs(task tags/type).

Implement compare_runs(run_a, run_b).

Implement compare_to_successful_cohort(run_id).

Include tool-sequence and metric differences.

US-6.4 — Agent-configuration inspection tools

User story: As the Judge, I need a focused evidence tool so I can investigate only the information relevant to my current hypothesis.

Acceptance criteria

Tool has a narrow schema and compact output.

Every result includes source run/version IDs.

Errors are returned as structured tool errors rather than exceptions that crash the graph.

Technical tasks

Implement inspect_system_prompt(version_id).

Implement inspect_tool_descriptions(version_id).

Implement inspect_retry_stop_policy(version_id).

Return hashes/versions for reproducibility.

US-6.5 — Historical diagnosis tools

User story: As the Judge, I need a focused evidence tool so I can investigate only the information relevant to my current hypothesis.

Acceptance criteria

Tool has a narrow schema and compact output.

Every result includes source run/version IDs.

Errors are returned as structured tool errors rather than exceptions that crash the graph.

Technical tasks

Implement find_similar_diagnoses(failure_type/evidence embedding or tags).

Return prior change, result, and whether it was accepted.

Do not let history override current evidence automatically.

Epic 7: Create Failure Scenarios and Labeled Judge Benchmark

Goal

Build known failure cases so Judge quality can be measured rather than judged by anecdotes.

Dependencies

Epics 1, 4–6

Exit milestone

A versioned benchmark contains traces with known failure labels and enough examples to compare generic vs specialized judging.

US-7.1 — Define the V1 failure taxonomy

User story: As the evaluator, I need a limited, clear taxonomy for the first target agent.

Acceptance criteria

5–8 failure categories are mutually understandable and documented.

Each category has positive examples and non-examples.

UNKNOWN is allowed for cases outside the taxonomy.

Technical tasks

Recommended V1 categories: wrong_tool_selection, repeated_retrieval, invalid_tool_arguments, ignored_tool_error, excessive_retry, premature_stop, unsupported_final_answer, inefficient_tool_sequence.

Write failure definition, observable symptoms, likely causes, and suggested optimization surfaces for each category.

US-7.2 — Generate labeled traces

User story: As the project owner, I need reproducible examples of each failure.

Acceptance criteria

At least 5 labeled traces per failure category exist before final evaluation.

Labels are assigned from known injected configuration changes or manual review, not by the same Judge being evaluated.

Healthy control traces are included.

Technical tasks

Create intentionally weak prompt/tool-description variants that induce specific failures.

Run the fixed target tasks to generate traces.

Store labels and rationale in benchmark/judge_labels.jsonl.

Link every label to Langfuse trace/run ID and target-agent version.

US-7.3 — Measure Judge diagnosis quality

User story: As the developer, I need to know whether specialization improves the Judge.

Acceptance criteria

Generic and target-aware Judges run on the same labeled traces.

Metrics include classification accuracy, precision/recall per failure, UNKNOWN rate, Judge tokens, Judge LLM calls, diagnostic tool calls, and latency.

Results are exported to CSV/JSON and summarized in a report.

Technical tasks

Create eval_judge.py.

Fix model, temperature, context budget, and max Judge steps for fair comparison.

Repeat uncertain cases if model nondeterminism materially affects results; report methodology.

Epic 8: Version Target-Agent Configuration and Generate Candidate Variants

Goal

Allow the Judge to produce safe, inspectable changes rather than editing the running agent in place.

Dependencies

Epics 4–7

Exit milestone

A diagnosis can produce a new immutable target-agent version whose diff is explicit and reversible.

US-8.1 — Create AgentVersion model

User story: As the optimizer, I need immutable versions so every run can be reproduced and rolled back.

Acceptance criteria

Every target run references exactly one agent_version_id.

Versions store system prompt, tool descriptions, retry/stopping policy, model config, parent version, and content hash.

Existing versions are never mutated.

Technical tasks

Create agent_versions table and repository layer.

Serialize version config as JSON plus normalized relational metadata as needed.

Add create_child_version(parent_id, patch) and load_version(version_id).

US-8.2 — Define allowed mutation actions

User story: As the system owner, I need the Judge to change only approved surfaces.

Acceptance criteria

V1 supports edits to system prompt, one or more tool descriptions, retry guidance/limits, stopping guidance, and tool-selection rules.

Judge cannot modify arbitrary Python source in V1.

Every candidate contains a human-readable change rationale and structured patch.

Technical tasks

Create CandidateChange schema with change_type, target, before_hash, proposed_value, rationale, expected_effect.

Build create_agent_variant(candidate_change) tool.

Reject changes that violate schema or attempt disallowed fields.

Epic 9: Build the Controlled Evaluation Runner

Goal

Run baseline and candidate agents under identical conditions and collect comparable results.

Dependencies

Epics 1–2, 8

Exit milestone

One command evaluates any agent version against a fixed dataset and persists run-level + aggregate metrics.

US-9.1 — Implement evaluation execution

User story: As the optimizer, I need a reproducible way to test agent variants.

Acceptance criteria

Same task IDs, model, temperature, tool data snapshot, and runtime limits are used for baseline and candidate.

Every evaluation run has a unique experiment_id and agent_version_id.

Individual task failures do not abort the entire experiment.

Technical tasks

Implement EvaluationRunner.run(version_id, dataset_id).

Use Langfuse Datasets/Experiments or a local dataset runner that pushes traces/results to Langfuse.

Record task correctness, tokens, tool calls, latency, errors, and terminal reason.

Support a small fast subset for development and full benchmark for promotion.

US-9.2 — Implement scoring

User story: As the comparison engine, I need trustworthy metrics for quality and efficiency.

Acceptance criteria

Task correctness is calculated from ground truth or task-specific scorer.

Efficiency metrics are programmatically calculated from traces.

Critical failure flags can be attached to task results.

Technical tasks

Implement per-task score interface.

Aggregate success_rate, mean/median tokens, mean tool calls, mean/p95 latency, tool error rate, and critical regression count.

Persist raw results so aggregate metrics can be recomputed.

Epic 10: Implement Comparison and Accept/Rollback Policy

Goal

Turn evaluation results into an explicit promotion decision instead of letting the LLM declare its own fix successful.

Dependencies

Epic 9

Exit milestone

Candidate variants are automatically accepted or rejected using configurable, auditable rules.

US-10.1 — Define V1 acceptance policy

User story: As the system owner, I need correctness protected before efficiency optimization.

Acceptance criteria

A candidate cannot be accepted if it creates a critical regression.

A candidate cannot be accepted if success drops below the configured quality floor.

When quality is equivalent or better, the policy prefers lower tokens/tool calls/latency according to configured priorities.

Decision includes machine-readable reasons.

Technical tasks

Start with simple rules: no critical regressions; success_rate >= baseline or configured tolerance; then require a minimum efficiency improvement or success improvement.

Make thresholds configuration, not constants.

Do not use the Judge LLM as the sole acceptance authority.

US-10.2 — Implement promotion and rollback

User story: As the optimizer, I need safe version transitions.

Acceptance criteria

Accepted variant becomes the active target-agent version.

Rejected variant remains stored for audit but is not active.

Rollback can restore any prior accepted version.

Every decision links diagnosis → candidate → evaluation → policy result.

Technical tasks

Create optimization_decisions table.

Implement accept_variant() and rollback_variant().

Add active_agent_version pointer/config.

Write integration tests for accepted, rejected, and critical-regression cases.

Epic 11: Close the Autonomous Optimization Loop

Goal

Connect diagnosis, mutation, evaluation, and promotion into one bounded LangGraph workflow.

Dependencies

Epics 4–10

Exit milestone

A single optimizer invocation can diagnose one target-agent problem, create a candidate, evaluate it, and finish with ACCEPT/ROLLBACK without manual orchestration.

US-11.1 — Build optimization graph

User story: As the project user, I need one coherent workflow instead of separate scripts.

Acceptance criteria

Workflow supports: load run → investigate → diagnose → create candidate → evaluate → compare → accept/rollback → terminate.

Every stage persists enough state to resume/debug.

Maximum optimization cycles and cost/tool budgets are enforced.

Technical tasks

Extend JudgeState or create OptimizationState.

Add graph nodes and conditional edges for diagnosis confidence, candidate generation failure, evaluation failure, accept, rollback.

Use LangGraph checkpointing for recoverable local runs if helpful.

Persist high-level optimization state in PostgreSQL for durable history.

US-11.2 — Handle failed optimization attempts

User story: As the system, I need graceful behavior when the Judge proposes a bad or invalid change.

Acceptance criteria

Invalid candidate patches are rejected before evaluation.

Evaluation infrastructure errors do not accidentally promote a candidate.

Judge may attempt a bounded second candidate if configured.

Terminal reason is explicit.

Technical tasks

Define error states: DIAGNOSIS_FAILED, CANDIDATE_INVALID, EVAL_FAILED, NO_IMPROVEMENT, ACCEPTED.

Add one optional retry path with a new hypothesis; avoid infinite self-optimization loops.

Epic 12: Optimization Memory and Similar-Failure Reuse

Goal

Let future Judge runs learn from previous diagnoses and rejected/accepted fixes without treating memory as truth.

Dependencies

Epics 7–11

Exit milestone

Judge can retrieve relevant past incidents and see whether prior fixes helped, while current trace evidence remains authoritative.

US-12.1 — Persist optimization history

User story: As the Judge, I need access to prior failures and outcomes.

Acceptance criteria

Diagnosis, evidence summary, candidate change, before/after metrics, and decision are stored.

Records are searchable by target agent, failure type, tags, and version.

Accepted and rejected fixes are both retained.

Technical tasks

Create diagnoses, candidate_changes, evaluations, optimization_decisions tables if not already covered.

Add repository/service methods and indexes.

Optionally add local embeddings later for semantic similarity; start with tags/failure type.

US-12.2 — Expose history as a Judge tool

User story: As the Judge, I want to know if a similar failure happened before.

Acceptance criteria

Tool returns concise prior cases with outcome, not entire old traces.

Judge prompt explicitly treats prior diagnosis as supporting evidence only.

History retrieval can be disabled for controlled benchmark comparisons.

Technical tasks

Implement find_similar_failures().

Log when memory influenced a diagnosis so its effect can be measured.

Epic 13: Project-Level Evaluation and Metrics

Goal

Produce the evidence required to show the system is effective and to identify where it fails.

Dependencies

Epics 7, 9–12

Exit milestone

A reproducible evaluation report compares Judge configurations and measures the optimizer’s effect on target-agent quality and efficiency.

US-13.1 — Compare generic vs target-aware Judge

User story: As the developer, I need to test the hypothesis that specialization helps.

Acceptance criteria

Both judges use the same model and labeled trace set.

Report diagnosis quality and judge resource usage.

Do not claim superiority if results do not support it.

Technical tasks

Metrics: accuracy, macro precision/recall/F1, UNKNOWN rate, input/output tokens, LLM calls, diagnostic tool calls, wall-clock latency.

Export results and create simple plots/tables for README.

US-13.2 — Measure optimizer impact on the target agent

User story: As the project owner, I need before/after evidence that accepted changes improve the target agent.

Acceptance criteria

Compare baseline accepted version with final accepted version on a held-out/fixed evaluation set.

Report success, tokens, tool calls, latency, error rate, and number of accepted/rejected candidate changes.

Evaluation set is not modified merely to make the optimized version look better.

Technical tasks

Create final_eval.py.

Store raw task-level output plus aggregate summary.

Add an ablation if useful: diagnosis only vs closed-loop optimizer.

Epic 14: Reliability, Safety, and Test Coverage

Goal

Make the optimizer trustworthy enough that failures are understandable and changes are reversible.

Dependencies

All core epics

Exit milestone

Unit/integration/e2e tests cover critical flows; no candidate can be promoted on incomplete evidence or broken evaluation.

US-14.1 — Unit-test contracts and tools

User story: As a maintainer, I need failures isolated to small components.

Acceptance criteria

Pydantic schemas, manifest parsing, TraceProvider normalization, diagnostic tools, scoring, and policy logic have unit tests.

Tests use fixtures and do not require live Langfuse unless marked integration.

Technical tasks

Create tests/fixtures/langfuse/*.json.

Mock Ollama responses for deterministic unit tests where possible.

Test token/context truncation boundaries and malformed trace payloads.

US-14.2 — Integration-test the closed loop

User story: As a maintainer, I need confidence that the full optimizer can safely reject and accept candidates.

Acceptance criteria

One fixture causes a known bad candidate and confirms rollback.

One fixture causes a known good candidate and confirms acceptance.

Telemetry outage/evaluation failure results in no promotion.

Technical tasks

Add Docker-backed integration profile.

Use a tiny 3–5 task dataset for CI/local integration tests.

Keep long local-model benchmark tests outside normal fast CI.

US-14.3 — Protect prompts/data and bound resource usage

User story: As the developer, I need local agent loops to stay safe and predictable.

Acceptance criteria

Secrets are excluded from trace payloads.

Judge/target loops have max steps, timeouts, and model/tool budgets.

Candidate changes cannot execute arbitrary shell commands.

Evaluation data snapshots are reproducible.

Technical tasks

Add redaction/filter hooks before telemetry.

Add per-run timeout and step budget.

Separate read-only diagnostic tools from mutation tools and expose mutation tools only after diagnosis stage.

Epic 15: Developer Experience, Documentation, and Demo

Goal

Make the system understandable and reproducible to someone who did not build it.

Dependencies

Core system complete

Exit milestone

A clean clone can run the demo, and the README shows one complete trace → diagnosis → variant → evaluation → accept/rollback example.

US-15.1 — Create reproducible commands

User story: As a reviewer, I need to run the system without learning the codebase first.

Acceptance criteria

README has setup commands for Windows/PowerShell and Docker services.

One command runs target demo; one runs Judge; one runs the closed-loop optimizer; one runs evaluation.

Expected outputs and troubleshooting notes are included.

Technical tasks

Create CLI entry points: run-target, judge-run, optimize-run, eval-judge, eval-target.

Add sample .env and model pull instructions.

Document Langfuse Cloud vs optional self-host configuration.

US-15.2 — Publish the technical story

User story: As a recruiter/interviewer, I need to understand what is yours vs infrastructure.

Acceptance criteria

README architecture explicitly labels Langfuse responsibilities and project-owned responsibilities.

Shows target-aware manifest example and Judge tool registry.

Shows real before/after metrics and at least one rejected candidate.

No placeholder metrics remain in the final public README.

Technical tasks

Add architecture diagram, optimization loop diagram, sample diagnosis JSON, candidate diff, evaluation table, and limitations section.

Document why Langfuse is used as telemetry while optimization remains project-owned.

Document known failure modes of the Judge and cases routed to the general fallback.

5. Recommended Repository Structure

agent-judge-optimizer/
├─ pyproject.toml
├─ .env.example
├─ docker-compose.dev.yml
├─ README.md
├─ configs/
│  ├─ agents/
│  │  └─ operations_agent.yaml
│  ├─ judge/
│  │  ├─ specialized.yaml
│  │  └─ general.yaml
│  └─ acceptance_policy.yaml
├─ data/
│  ├─ documents/
│  ├─ seed/
│  └─ tasks/
├─ src/
│  ├─ target_agent/
│  │  ├─ graph.py
│  │  ├─ state.py
│  │  ├─ tools.py
│  │  └─ prompts.py
│  ├─ judge/
│  │  ├─ graph.py
│  │  ├─ state.py
│  │  ├─ prompts.py
│  │  ├─ diagnosis.py
│  │  └─ tool_registry.py
│  ├─ diagnostics/
│  │  ├─ trace_tools.py
│  │  ├─ metric_tools.py
│  │  ├─ comparison_tools.py
│  │  ├─ config_tools.py
│  │  └─ history_tools.py
│  ├─ telemetry/
│  │  ├─ provider.py
│  │  └─ langfuse_provider.py
│  ├─ optimization/
│  │  ├─ variants.py
│  │  ├─ mutations.py
│  │  ├─ policy.py
│  │  └─ controller.py
│  ├─ evaluation/
│  │  ├─ runner.py
│  │  ├─ scorers.py
│  │  ├─ metrics.py
│  │  └─ judge_benchmark.py
│  ├─ persistence/
│  │  ├─ models.py
│  │  ├─ repositories.py
│  │  └─ migrations/
│  └─ common/
│     ├─ schemas.py
│     ├─ logging.py
│     └─ config.py
├─ benchmark/
│  ├─ judge_labels.jsonl
│  ├─ failure_scenarios/
│  └─ reports/
├─ scripts/
│  ├─ seed_data.py
│  ├─ run_target.py
│  ├─ judge_run.py
│  ├─ optimize_run.py
│  └─ final_eval.py
└─ tests/
   ├─ unit/
   ├─ integration/
   └─ fixtures/

6. Target-Agent Manifest: Example Contract

The manifest is central to the specialized-Judge design. It allows the same Judge framework to be configured for a different target without hardcoding domain rules in the graph.

agent_id: operations_react_v1
domain: internal_operations

tools:
  search_documents:
    purpose: "Retrieve internal policy and procedural text"
    expensive: false
  query_records:
    purpose: "Read structured customer/order/incident data"
    expensive: false
  calculator:
    purpose: "Perform arithmetic from retrieved numeric evidence"
    expensive: false
  lookup_policy:
    purpose: "Fetch authoritative policy by identifier"
    expensive: false

behavioral_rules:
  - "Do not repeat substantially equivalent retrieval queries without new evidence."
  - "Do not ignore a tool error and pretend the requested evidence was retrieved."
  - "Use calculator for nontrivial arithmetic."
  - "Final factual claims must be supported by retrieved data."

failure_taxonomy:
  - wrong_tool_selection
  - repeated_retrieval
  - invalid_tool_arguments
  - ignored_tool_error
  - excessive_retry
  - premature_stop
  - unsupported_final_answer
  - inefficient_tool_sequence

judge_tools:
  - get_trace_summary
  - list_tool_calls
  - inspect_tool_call
  - analyze_token_usage
  - analyze_latency
  - compare_to_successful_cohort
  - inspect_system_prompt
  - inspect_tool_descriptions
  - find_similar_failures

optimization_priorities:
  correctness: 1.0
  tokens: 0.35
  tool_calls: 0.35
  latency: 0.20

7. Minimum Persistent Data Model

Entity

Purpose

Key fields

agent_versions

Immutable target-agent configurations.

id, parent_id, prompt, tool_descriptions_json, retry_policy_json, stop_policy_json, model_config_json, content_hash, status, created_at

target_runs

Index target executions and correlate Langfuse trace IDs.

run_id, trace_id, task_id, agent_version_id, model_id, status, created_at

judge_runs

Track Judge investigations.

id, target_run_id, manifest_version, mode(specialized/general), model_id, diagnosis_id, tokens, tool_calls, latency

diagnoses

Structured root-cause result.

id, failure_type, summary, root_cause, severity, confidence, evidence_json, recommended_change_type

candidate_changes

Versioned proposed optimization.

id, diagnosis_id, parent_version_id, candidate_version_id, change_type, patch_json, rationale

evaluation_runs

One benchmark execution of one agent version.

id, agent_version_id, dataset_version, started_at, completed_at, aggregate_metrics_json

evaluation_items

Per-task result.

evaluation_run_id, task_id, success, tokens, tool_calls, latency_ms, errors_json, scores_json

optimization_decisions

Promotion history.

id, baseline_version_id, candidate_version_id, policy_version, decision, reasons_json, created_at

8. Practical Build Sequence (8-Week Baseline)

This is sequencing, not a deadline: Do not advance because a week ended; advance when the milestone exit criteria are met. A strong partial implementation is better than a rushed full loop.

Week

Primary work

Exit criteria

1

Epic 0 + start Epic 1

Repo, Ollama, Postgres, and target tools work; target agent can run simple tasks.

2

Finish Epic 1 + Epic 2

20-task target dataset exists; target traces are complete and retrievable through TraceProvider.

3

Epics 3–4

Judge loads trace summary, autonomously uses diagnostic tools, and emits validated diagnosis JSON.

4

Epics 5–7

Manifest-driven specialized Judge + fallback exist; labeled failure benchmark has initial examples.

5

Epic 8 + start Epic 9

Immutable agent versions and controlled candidate changes exist; evaluation runner can execute one version.

6

Finish Epic 9 + Epic 10

Baseline/candidate comparison and automatic accept/rollback work.

7

Epics 11–13

Full optimizer loop works; generic vs specialized Judge and target before/after metrics are collected.

8

Epics 14–15

Reliability tests, Docker/dev scripts, README, diagrams, final benchmark report and demo are complete.

9. Exactly What to Implement First

Day 1: Environment + one local tool call

Create the repository structure and Python 3.11 virtual environment.

Install LangGraph, LangChain core/Ollama integration, Langfuse SDK, Pydantic, SQLAlchemy, pytest, and the Ollama Python client.

Pull Qwen3 4B and verify normal generation, tool calling, and schema-constrained JSON output.

Start PostgreSQL through Docker Compose and verify a Python connection.

Commit the clean foundation before writing the agent.

Day 2: Target agent vertical slice

Create 2–3 small local documents and a tiny structured data file/database.

Implement search_documents, query_records, and calculator.

Build a minimal LangGraph ReAct loop with a maximum-step limit.

Create five target tasks and run them manually.

Version the target prompt/tool descriptions in config instead of embedding them in graph code.

Day 3: Observability vertical slice

Create Langfuse project and add callback instrumentation.

Run the five tasks and verify each trace contains LLM calls, tool calls, timing, token usage, task_id, and agent_version_id.

Implement TraceProvider + LangfuseTraceProvider.get_trace_summary().

Write a small CLI that prints a normalized TraceSummary from a run ID.

Do not start automatic optimization until this output is reliable.

10. Engineering Gates Before Moving to the Next Layer

Gate

Must be true before continuing

Target-agent gate

At least 80% of the initial easy tasks run end-to-end; errors produce traces instead of unexplained crashes.

Telemetry gate

A run can be reconstructed sufficiently from TraceProvider; task/version IDs are never missing.

Judge gate

Judge selects at least two different diagnostic tools on different failure cases and outputs schema-valid diagnoses.

Specialization gate

Changing only the manifest changes available failure categories/tool set; source code remains unchanged.

Benchmark gate

Failure labels come from known injections/manual review, not the Judge itself.

Mutation gate

All target-agent changes produce a new immutable version; no in-place mutation.

Evaluation gate

Baseline and candidate use exactly the same dataset/configuration snapshot.

Promotion gate

No candidate can be promoted when evaluation is incomplete, crashed, or contains a critical regression.

11. Metrics to Capture From the Beginning

Layer

Metric

Why it matters

Target agent

Task success rate

Primary quality metric.

Target agent

Input/output/total tokens per task

Measures inference efficiency.

Target agent

Tool calls per task

Measures trajectory efficiency.

Target agent

Tool error/retry count

Reveals operational failures.

Target agent

Latency per task

Measures performance.

Judge

Diagnosis accuracy / F1 on labeled traces

Measures Judge quality.

Judge

UNKNOWN / fallback rate

Shows where specialization is insufficient.

Judge

Tokens per diagnosis

Tests the specialization-cost hypothesis.

Judge

Diagnostic tool calls per diagnosis

Measures investigation complexity.

Judge

Latency per diagnosis

Measures practical cost.

Optimizer

Candidate acceptance rate

Shows how often proposed fixes survive evaluation.

Optimizer

Rollback/rejection reasons

Shows whether the safety gate is doing useful work.

Optimizer

Baseline vs final target metrics

Shows actual value delivered by optimization.

12. Risk Register and Mitigations

Risk

Why it happens

Mitigation

Local model gives inconsistent tool calls

4B/8B local models are weaker than premium hosted models.

Keep tools narrow, descriptions explicit, temperature low, structured outputs validated, and step budgets small. Use 8B for serious evaluation runs.

Judge misses unknown failure modes

Target-specific taxonomy can create tunnel vision.

Allow UNKNOWN and route low-confidence cases to a broader fallback Judge.

Judge context grows too large

Raw traces can exceed practical local context/VRAM.

Expose trace data through retrieval tools and compact summaries; never paste full traces by default.

Optimizer “improves” cost but hurts correctness

Efficiency is easier to reduce than quality is to preserve.

Acceptance policy protects correctness/critical regressions first, then optimizes efficiency.

Benchmark becomes biased

If failures are created after seeing Judge behavior, results can overfit.

Version the benchmark, keep a held-out subset, and separate injected/manual labels from Judge output.

Langfuse dependency leaks into core logic

Direct SDK calls spread throughout Judge.

Use TraceProvider interface and internal normalized schemas.

Optimization loop runs forever

Judge can keep trying variants.

Set max candidate attempts/cycles and explicit terminal reasons.

Candidate cannot be reproduced

Prompts/configs overwritten in place.

Use immutable AgentVersion records and content hashes.

Hardware pressure

RTX 4050 has 6 GB VRAM.

Use 4B for iteration, 8B for final Judge runs, 8K-ish context initially, compact tool outputs, and sequential target/Judge execution.

13. Definition of Done for the Project

Target agent has a versioned task dataset and at least four meaningful tools.

Langfuse traces every target run with stable task, agent-version, model, token, latency, and tool-call metadata.

Judge is a true tool-using LangGraph agent: it autonomously chooses diagnostic tools and can take different investigation paths.

Target-agent manifest configures specialized failure taxonomy, relevant Judge tools, behavioral rules, and optimization priorities.

General fallback Judge handles low-confidence/unknown cases.

At least five distinct failure categories have labeled benchmark examples.

Generic vs specialized Judge comparison is reproducible and reports both quality and resource usage.

Judge can generate a controlled, immutable target-agent variant.

Evaluation runner compares baseline and candidate on the same fixed workload.

Acceptance policy automatically accepts or rolls back with explicit reasons and never promotes incomplete/failed evaluations.

Optimization history is stored in PostgreSQL and prior incidents can be queried by the Judge.

At least one complete optimization cycle is demonstrated with real before/after metrics; at least one candidate rejection/rollback is also demonstrated.

Repository setup, demo commands, architecture, limitations, and measured results are documented without placeholder numbers.

14. Current Technical References Used for This Plan

These references were checked while creating the plan. They are included so implementation details can be revalidated if APIs change.

LangGraph reference — stateful multi-step agent workflows: https://reference.langchain.com/python/langgraph/overview

LangGraph persistence concepts: https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/persistence.mdx

Langfuse LangChain/LangGraph integration: https://langfuse.com/integrations/frameworks/langchain

Langfuse LangGraph integration: https://langfuse.com/integrations/frameworks/langgraph

Langfuse tracing: https://langfuse.com/docs/observability/get-started

Langfuse datasets and experiments: https://langfuse.com/docs/evaluation/experiments/datasets

Langfuse evaluation concepts: https://langfuse.com/docs/evaluation/core-concepts

Langfuse prompt management: https://langfuse.com/docs/prompt-management/overview

Ollama tool calling: https://github.com/ollama/ollama/blob/main/docs/capabilities/tool-calling.mdx

Ollama structured outputs: https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx

Ollama context length: https://github.com/ollama/ollama/blob/main/docs/context-length.mdx

Appendix A. Implementation Task Tracker

Done

Epic

Task

Owner/Notes

Evidence/PR

☐

0

Repo/env baseline

☐

0

Ollama tool + structured-output smoke tests

☐

0

Postgres + migrations

☐

1

Target data/tools

☐

1

Target LangGraph loop

☐

1

Initial task dataset

☐

2

Langfuse tracing

☐

2

TraceProvider abstraction

☐

3

Normalized telemetry schemas

☐

3

JudgeState

☐

4

Judge tool loop

☐

4

Structured Diagnosis

☐

5

AgentManifest

☐

5

Specialized/general routing

☐

6

Trace tools

☐

6

Metric tools

☐

6

Cross-run tools

☐

6

Config inspection tools

☐

6

History tools

☐

7

Failure taxonomy

☐

7

Labeled trace set

☐

7

Judge benchmark

☐

8

AgentVersion store

☐

8

Candidate mutation tools

☐

9

Evaluation runner

☐

9

Scoring/aggregation

☐

10

Acceptance policy

☐

10

Promotion/rollback

☐

11

Full optimization graph

☐

11

Failure handling

☐

12

Optimization memory

☐

12

History retrieval

☐

13

Generic vs specialized evaluation

☐

13

Final target-agent before/after evaluation

☐

14

Unit/integration tests

☐

14

Resource/security bounds

☐

15

CLI/demo scripts

☐

15

README/architecture/results

Recommended first commit: Stop after Epic 0 foundation + one Ollama smoke test. Then implement the target-agent vertical slice. Avoid building the Judge prompt before you have real traces to inspect.
