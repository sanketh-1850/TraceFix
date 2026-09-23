# Epic 1 verification

Implemented on 2026-09-17: a local, controlled order-support ReAct agent using
LangGraph, Ollama Qwen3 4B, and the existing MariaDB server.

## Delivered

- Four read-only tools: deterministic document search, filtered business record
  queries, bounded decimal arithmetic, and exact policy lookup.
- Migration `0002_target_data`, 10 synthetic customers, 8 products, 30 orders, 31
  line items, and six policy documents. Repeat seeding is idempotent and conflicts
  abort without overwriting existing records.
- Versioned prompt, tool descriptions, and budgets; validated answers with facts
  and evidence IDs; controlled retries, answer repair, and explicit terminal reasons.
- Twenty independently specified tasks: 10 easy, 8 multi-tool, 2 recovery cases.
  The runtime receives only each task's public ID and question. Scoring checks facts
  and required evidence independently of the target model.
- Seed, single-run, fixed-suite evaluation, and labelled live fault-injection commands.
  Local records preserve model settings, hashes, observations, answers, metrics, and
  partial failures. No Langfuse integration or Judge implementation is included yet.

## Verification

- 41 unit tests pass, including all existing Epic 0 tests.
- Three live MariaDB integration tests pass. Migration rollback/re-upgrade uses only
  randomly named disposable databases; the project's existing metadata is preserved.
- Ruff, dependency consistency, entry-point help, repeat seeding, and PowerShell
  syntax checks pass.
- Live Qwen3 4B baseline: **14/20 tasks passed (70%)**, including **10/10 easy tasks**
  against the required 8/10 threshold. All 20 tasks were attempted on the same
  database/document snapshot and agent configuration.
- Task T18 demonstrates sequential reasoning across observations: query order
  ORD-010, call the calculator with the returned line-item amounts, then answer
  `$95.00` with both observations cited. It used three model calls and two tools.
- T19 correctly handles an absent order and cites the failed lookup.

| Failed task | Observed failure |
| --- | --- |
| T11, T12, T15, T17, T20 | Generation reached the 2048-token cap; partial runs were retained and scored as failures. |
| T16 | Correct eligibility/refund facts, but no required calculator call/evidence. |

The dataset and expected answers were not changed to improve these results. This
establishes a measured baseline with imperfections for later diagnosis and optimization;
it does not claim all benchmark questions are solved.

Committed evidence: [baseline summary](examples/epic1-baseline-summary.json) and
[successful sequential run](examples/epic1-success.json). All raw baseline records
remain locally in `artifacts/epic1-baseline/`; individual run-file names in the summary
refer to that directory. The summary uses explicit `input_tokens` labels for input
usage. The first run's original local summary used the shorter label `tokens` for
the same input counts.

The separate live fault-injection demo also completed: `query_records` returned an
explicit `injected_unavailable` error. The model produced valid answer JSON but
incorrectly described the order as not found. The scorer rejected it for incorrect
status and missing required source evidence. This is a **completed execution with
a failed task**, not a successful answer or an infrastructure crash. The failure is
labelled and excluded from the 20-task baseline. See the [injected run](examples/epic1-injected-failure.json)
and its [score](examples/epic1-injected-score.json).

Epic 1 meets its implementation gates: all four tools work, the default easy-task gate
is passed, sequential multi-step execution is demonstrated, and both successful and
imperfect trajectories are retained. The six baseline failures remain limitations.

## Implementation adjustments and limits

The first live pilot with disabled thinking and a 512-token cap truncated before
calling a tool. With this installed Qwen3 template, enabling reasoning separates it
from answer text. The target configuration therefore uses reasoning enabled and a
2048-token output cap. The standalone Epic 0 smoke settings are unchanged. Target
runs retain an 8192-token context, temperature 0, seed 42, 10 model calls, 12 tool
executions, two retries of a failed tool/argument combination, one answer-format
repair, and a 300-second deadline. Token usage includes reasoning; reasoning text
is not saved in run records.

This is a deliberately small synthetic benchmark, not evidence of production support
quality. The deterministic scorer checks declared facts, evidence IDs, and calculator
results where required; it cannot certify every natural-language claim. Correct facts
without required supporting evidence still fail the task. Expected tool coverage is
reported separately. Model generation is not guaranteed deterministic across hardware
or runtime versions even with a fixed seed. Failed cases remain in the results.

All tools are read-only. A database operation already in progress at the run deadline
may finish its read within the configured database I/O timeout. Evaluation records
infrastructure failures and continues to the next task. Optional Docker deployment was
not needed; the existing MariaDB server was used.

Epic 2 remains necessary to complete milestone M1's observability requirements.
