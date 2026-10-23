# TraceFix

TraceFix is an Agent-as-a-Judge system that investigates why AI agents fail and tests changes to improve them. It follows an agent's execution from the initial request through its model responses, tool calls, and final answer, then uses that evidence to diagnose problems and evaluate possible fixes.

A failed task rarely tells the whole story. An agent might choose the wrong tool, repeat an unhelpful search, ignore an error, stop too early, or produce an answer its sources do not support. TraceFix examines the decisions behind the result. Its Judge selects diagnostic tools to inspect relevant observations, tool arguments, configuration, and previous runs. Each diagnosis records the likely root cause, supporting evidence, confidence, and a recommended change. When the evidence is insufficient, the Judge can return an unknown diagnosis or use a general fallback.

The diagnosis feeds a controlled optimization loop. TraceFix creates a candidate version with changes limited to approved configuration, such as prompts, tool descriptions, retry limits, and stopping guidance. Each version preserves its parent, the exact change, and the reason for it. The candidate is evaluated against the baseline using the same frozen tasks, data, model settings, and scoring rules.

Promotion depends on measured results. A deterministic policy checks task correctness, critical regressions, and improvements in quality or efficiency. Incomplete evaluations and failed checks block promotion. Rejected candidates remain in the experiment history, and previous versions remain available for rollback. Every decision can be traced back to the diagnosis, candidate, and evaluation that produced it.

TraceFix works across two targets through shared execution and evaluation adapters. The first is an order-support agent that answers questions using synthetic customer and order records, document search, a calculator, and policy lookup. The second is an independent ReAct agent from tau3-bench, evaluated with the benchmark's own tasks, policies, tools, data, and official evaluator. Separate target manifests describe each agent's tools, expected behavior, and allowed changes while the Judge and optimizer share the same core workflow.

Evaluation also compares generic and target-aware Judges on the same labeled traces. It measures diagnosis accuracy, precision, recall, inference cost, and latency alongside the effect of proposed fixes on target performance. Development tasks support optimization, while held-out tasks provide a separate final assessment.

The system uses Python and LangGraph for agent workflows, Langfuse for observability, Ollama for local model inference, and MariaDB for durable experiment history. It retains accepted and rejected changes so later investigations can draw on previous findings while grounding each new diagnosis in the current trace.
