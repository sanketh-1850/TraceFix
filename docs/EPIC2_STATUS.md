# Epic 2 observability status

Completed and verified on **2026-10-29 (America/Chicago)** against US Langfuse Cloud
Hobby with Python SDK **4.15.6**. The real Judge graph belongs to Epic 4.

## Acceptance results

| Check | Result |
| --- | --- |
| Cloud configuration | Supplied keys authenticated; tracing enabled; US base URL resolved correctly |
| Four-task smoke profile | T01, T06, T08, T10 passed correctness and remote telemetry verification |
| Frozen development profile | All 14 executions finished; all 14 traces verified remotely |
| Development correctness | 8/14 on this run; the historical 9/14 baseline is preserved |
| Separate failures | Injected tool outage, simulated model error, simulated truncation: all three traces verified |
| Judge recorder | Generic and specialized simulated runs verified with independent trace IDs |
| Offline tests | 75 passed, including both providers against three sanitized Cloud fixtures |
| Live integration tests | All six MariaDB/Ollama/telemetry checks passed |
| Integrity and dependencies | A0 hashes, Ruff, and `pip check` passed |
| MariaDB schema | `0003_target_runs` at head; all 21 target-run index rows verified |
| Held-out workload | No held-out tasks executed for Epic 2 acceptance |

The development run used 23 model calls, 11 tool calls, one expected not-found error,
no tool retries, 24,809 input tokens, 24,918 output tokens, and 435,902.881 ms of A0
execution time. T08, T11, T12, T15, and T17 truncated; T16 omitted required calculator
evidence. The earlier baseline had four truncations and the same evidence failure.
The additional T08 truncation is reported as observed model variation. Prompts,
budgets, tasks, and scoring were not tuned for this verification.

The injected tool outage produced an error observation and a structurally completed
answer that failed correctness scoring. The other two failure cases use deterministic
LangChain model fixtures, labelled `fixture-model` and ad hoc. A model error has
unknown token usage; explicit zero usage remains zero. Cloud's legacy zero aggregates
with empty usage details are treated as unknown rather than invented measurements.

Sanitized evidence, every run/trace ID, correctness results, normalized metrics,
Judge results, and the official CLI audit are retained in
[epic2-verification.json](examples/epic2-verification.json). Original run files remain
under ignored `artifacts/epic2/`. Three captured Cloud responses in
`tests/fixtures/telemetry/` support offline provider contract tests.

## Real trace examples

These links require access to the configured private Langfuse project.

| Example | Trace |
| --- | --- |
| Successful T01 record lookup | [Target A](https://us.cloud.langfuse.com/project/cmvuamuz900lbad0eendys9z5/traces/2284a5306abf4765b2f9bff30b1c12a4) |
| Successful multi-tool T14 | [Record and policy](https://us.cloud.langfuse.com/project/cmvuamuz900lbad0eendys9z5/traces/157c76182cc442c99335bae020db88db) |
| Failed T12 truncation | [Failed A0](https://us.cloud.langfuse.com/project/cmvuamuz900lbad0eendys9z5/traces/c1a35343f1234abeb4edf7d2bf04b2e4) |
| Injected record-tool outage | [Ad hoc failure](https://us.cloud.langfuse.com/project/cmvuamuz900lbad0eendys9z5/traces/629a16d56f88485da0d44d5f21fc40d1) |
| Simulated model outage | [Model error](https://us.cloud.langfuse.com/project/cmvuamuz900lbad0eendys9z5/traces/73a76b1f62444cad92bd0f8f505cff5e) |
| Generic simulated Judge | [Judge](https://us.cloud.langfuse.com/project/cmvuamuz900lbad0eendys9z5/traces/89d6a81d517f4410a1a11e3454a84f7a) |
| Specialized simulated Judge with fallback | [Judge](https://us.cloud.langfuse.com/project/cmvuamuz900lbad0eendys9z5/traces/7ede3e9a88574ac4ab20541936d09a4d) |

The official CLI fetched and audited target, failure, and Judge observations for
meaningful root input/output, model names, completed generations, tool structure,
and absence of configured secrets. Judge profiles additionally checked usage,
diagnostic tools, source-run links, fallback flags, diagnosis, timing, hierarchy,
and exclusion from the target-run index.

## Implementation and authority

The wrapper supplies frozen A0 with a bound Ollama model using Langfuse callbacks
and a tool-environment decorator. Supported target, evaluation, baseline, and failure
commands use it. The historical `python -m tracefix.target_agent.cli` remains an
untraced reference path. No frozen implementation file was edited.

| Information | Authoritative source and limits |
| --- | --- |
| Identity and expected calls | MariaDB `target_runs`; maps A0's run ID to its trace ID |
| Task, version, benchmark, dataset, model | Frozen snapshots and index, compared against remote root metadata |
| Execution status and terminal reason | A0's local result; completed execution does not imply a correct answer |
| Correctness | Independent scorer and evaluation summary; never supplied to the target model |
| Executed tools | Wrapper count, including a read that times out before A0 receives it |
| Returned tool observations | Unchanged A0 result; remote metadata links its observation and call IDs |
| Observation IDs, hierarchy, I/O, timing | Retrieved Langfuse observations; I/O is redacted and bounded |
| Token usage | Available generation usage details; absent values remain null, explicit zero remains zero |
| Latency | Local A0 duration for comparisons; span duration for telemetry inspection |
| Cost | Not fabricated from token counts for local Ollama |

The five TraceProvider methods return Pydantic records without SDK objects. Both
providers share normalization and verification. Observations v2 retrieval uses fixed
UTC windows, all cursor pages, deduplication, deterministic ordering, bounded retries,
and Hobby-aware request pacing. Verification checks identity/outcome, completed spans,
model identity, counts, ancestry, and tool IDs/mappings. Every normalized evidence
method is exercised against a single fetched snapshot. Foreign and Judge observations
cannot establish a verified target trace. An SDK-generated parent outside the exported
logical root is allowed; all descendants must lead to the Target A root.

Callback setup, span entry/update/exit, flush, and shutdown failures cannot repeat
inference or tool execution. Local results survive telemetry outages. Known export
finalization failures update durable rows to `unavailable`; `pending` means unverified,
and partial retrieval stays `incomplete`. Flushing alone never establishes `verified`.
A timed-out read may finish after its root span; both executions and returned A0
observations are retained separately. Secrets and oversized values are masked before
export. Reasoning text stays redacted under the existing project policy; reported
token usage can include reasoning.

## Configuration and reproduction

Keep credentials in ignored `server.env`:

```dotenv
LANGFUSE_ENABLED=true
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=<project public key>
LANGFUSE_SECRET_KEY=<project secret key>
LANGFUSE_ENVIRONMENT=development
```

`LANGFUSE_HOST` remains an alias. Process environment overrides file values across
both names. Conflicting URLs within one source fail clearly. Settings load before
client initialization and the resolved URL is passed explicitly.

With MariaDB and Ollama running:

```powershell
.venv/Scripts/python.exe scripts/verify_epic2.py smoke
.venv/Scripts/tracefix-eval-target-a0.exe --split development --output-dir artifacts/epic2/development
.venv/Scripts/tracefix-trace.exe verify-evaluation artifacts/epic2/development/summary.json --output artifacts/epic2/development/telemetry-verification.json
.venv/Scripts/python.exe scripts/verify_epic2.py failures
.venv/Scripts/python.exe scripts/verify_epic2.py judge --run-id <verified_target_run_id>
```

Choose a new output directory to preserve an earlier profile's summary. The A0 command
returns success when every benchmark item was recorded, including correctness failures.
The batch verifier separately fails for missing/unverified runs, saves progress, and
can be rerun without inference. It requires the exact frozen development task set.

Inspect runs with `tracefix-trace list`, `summary <run_id>`, `tools <run_id>`,
`observation <run_id> <observation_id>`, `metrics <run_id>`, and `verify <run_id>`.
Verification polls incomplete ingestion for up to 60 seconds, plus bounded API time.
Authorization failures stop immediately; rate limits honor `Retry-After`. During an
outage, summary/metrics display local fields with remote-only metrics unknown.

## Limits and references

This closes M1's Target A observability gate. Judge recordings are simulated; Epic 4
will connect the recorder to the real graph. Concrete execution/evaluation adapters
remain Epic 3 work. Cloud verification is evidence at the recorded time; Hobby's API
read window is limited, so the saved fixtures and report preserve the acceptance record.

The official Langfuse skill was installed in the user's Codex skills directory and
used for documentation-first instrumentation and the run/fetch/audit cycle. References:
[official skill](https://github.com/langfuse/skills/tree/main/skills/langfuse),
[best practices](https://langfuse.com/docs/observability/best-practices),
[Public API](https://langfuse.com/docs/api-and-data-platform/features/public-api),
[API limits](https://langfuse.com/faq/all/api-limits), and
[read-window limits](https://langfuse.com/docs/administration/data-deletion).
