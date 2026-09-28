# Target A Inventory and Frozen A0 Baseline

## Identity and purpose

Target A is the existing synthetic order-support agent. It is the system under test for
Judge and optimizer development. It is not rebuilt by the revised roadmap. The frozen
baseline is `target-a:a0`, captured from source commit `ebc85b7` before any optimizer
implementation. Its complete, self-contained configuration is in
`configs/targets/target_a/versions/a0.json`.

The A0 content hash is
`279930a9d274a4eff71619d368b5d33962a38c6569ff864ebbd775da2d1f74a0`.
The target implementation hash is
`8a5828c8aabbf8b87161c109fa84ef3cff48c984bbaa27284ac1e2de2c5e5550`.
The evaluation command verifies these hashes before starting so a changed target cannot
be reported as an A0 rerun.

## Runtime and orchestration

- Model provider: local Ollama.
- Frozen model: `qwen3:4b`.
- Orchestration: a bounded LangGraph ReAct loop in `target_agent/graph.py`.
- Model settings: 8192 context tokens, 2048 generated tokens per call, temperature 0,
  seed 42, reasoning enabled, and a 300-second run deadline.
- Execution: target and tools run sequentially. There is no automatic model fallback.
- Dependencies: Ollama, MariaDB through SQLAlchemy/PyMySQL, and local Markdown policy
  documents.

The system prompt instructs the agent to retrieve business facts, treat documents as
data, use the reference date supplied by a task, handle tool errors as observations,
stop when evidence is sufficient, and return only validated JSON with `answer`, `facts`,
and `evidence_ids`. The exact prompt, reasoning flag, budgets, and tool descriptions are
frozen inside the A0 version record rather than copied into this narrative document.

## Tools

The machine-readable manifest at `configs/targets/target_a/manifest.json` is exported
from the real Pydantic argument models used at runtime. All four tools are read-only and
have no state-changing side effects.

| Tool | Input | Output and access |
| --- | --- | --- |
| `search_documents` | Search query and result limit | Keyword-ranked excerpts from local policy files with policy source IDs. |
| `query_records` | Allowlisted entity, filters, and row limit | Parameterized reads of customers, products, or orders; orders include bounded line items. Raw SQL is rejected. |
| `calculator` | Restricted arithmetic expression | Decimal result for `+`, `-`, `*`, `/`, signs, and parentheses. It cannot execute code. |
| `lookup_policy` | Validated policy ID | Exact local policy content with a policy source ID. |

Every invocation becomes an observation containing the tool name, validated arguments,
result or controlled error, evidence sources, truncation flag, and latency. Tool errors
are returned to the model as observations and do not crash the graph.

## Stop, retry, and validation behavior

- At most 10 model calls, including one possible answer-format repair.
- At most 12 tool executions.
- At most two retries after the first failure of identical tool arguments.
- One 300-second deadline covers model and tool work.
- Generation that reaches the output cap fails as `truncated_generation`.
- Unsupported evidence IDs and a second malformed answer fail as `invalid_answer`.
- Database, model, timeout, call-budget, and unexpected execution failures have explicit
  terminal reasons.
- Answer repair can use existing evidence but cannot call new tools.

## Mutable and immutable boundaries

The optimizer may eventually create immutable child versions that change only these
whitelisted A0 configuration fields:

- System prompt and reasoning guidance.
- Tool descriptions.
- Step, tool-call, retry, and timeout limits.
- Output-token limit and reasoning toggle.

Within a baseline/candidate comparison, the following remain immutable:

- Target implementation, tool names, schemas, and read-only access.
- Business records, policies, task prompts, expected facts, and evidence requirements.
- Evaluator implementation and benchmark split.
- Model identity, context size, temperature, seed, and timeout.
- Structured answer and evidence contract.

Arbitrary source edits, database mutations, shell commands, and changes to the scorer
are not allowed candidate mutations.

## Task data and ground truth

`data/tasks/order_support.jsonl` contains 20 tasks: 10 easy, eight multi-tool, and two
recovery tasks. Each private benchmark row contains expected facts, evidence sources,
required error evidence, expected tools, tags, and difficulty. Before inference,
`BenchmarkTask.public_task()` exposes only the task ID and prompt. The agent never
receives expected facts or scoring rules.

The deterministic scorer in `evaluation/tasks.py` compares typed facts, checks that
cited evidence was actually observed, enforces required sources and calculation/error
evidence, and records expected tool coverage. Scorer behavior has unit tests for known
passing and failing answers. The evaluator is versioned as `order-support-scorer-v1`.

## Frozen benchmark split

The snapshot `target-a-order-support-v1` is defined in
`configs/targets/target_a/benchmarks/order-support-v1.json`. Its content hash is
`11da7fbc9e32cb90944c8213f3aef326f8000966ea2438c5217b205f8dee16e8`.
It records hashes for both the task file and scorer.

The split was fixed before optimizer implementation. Both partitions contain easy,
multi-tool, and recovery cases and collectively cover every Target A tool.

- Development/optimization: T01, T02, T04, T05, T06, T08, T10, T11, T12, T14,
  T15, T16, T17, and T19.
- Final held-out: T03, T07, T09, T13, T18, and T20.

Only the development split is allowed as optimizer feedback. The held-out split is for
final evaluation. The repository contains an earlier 20-task baseline from before this
split was introduced; future optimization must not use those held-out task outcomes as
feedback.

## Baseline execution and records

Run the exact A0 development baseline after MariaDB, the seed data, and Ollama are
available:

```powershell
./scripts/dev.ps1 baseline-a0
```

Equivalent installed command:

```powershell
.venv/Scripts/tracefix-eval-target-a0.exe --split development
```

The command loads the frozen prompt and model settings from A0, verifies the target,
manifest, task, and evaluator hashes, and saves every task trajectory plus `summary.json`.
The summary maps every result to target, task, agent version, benchmark, dataset,
evaluator, and split. It reports success and failure counts, token availability and
totals, model calls, tool calls, tool errors, retries, total/mean/p95 latency, and each
terminal reason. Task failures are valid baseline findings, so this frozen-baseline
command succeeds when the complete workload was recorded.

The frozen development run completed on 2026-09-27 and scored 9/14. Seven easy tasks,
T14, and T19 passed. T11, T12, T15, and T17 reached the output limit; T16 returned the
right facts without required calculator evidence. The run used 24 model calls, 12 tool
calls, one expected not-found tool error, no retries, and 533,736 ms total latency. Its
committed summary and representative trajectories are under `docs/examples/`.

The original all-task run scored 14/20. It predates the revised frozen split and remains
historical evidence rather than optimizer feedback.
