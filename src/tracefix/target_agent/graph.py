"""Bounded ReAct workflow. The graph only receives public task input, never a rubric."""

import asyncio
import json
from datetime import datetime, timezone
from time import perf_counter
from typing import TypedDict
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from tracefix.common.config import Settings, load_settings
from tracefix.target_agent.config import AgentConfig
from tracefix.target_agent.data import snapshot
from tracefix.target_agent.schemas import TargetAnswer, TargetRunResult, TargetTask
from tracefix.target_agent.tools import ToolEnvironment


class TargetState(TypedDict):
    messages: list
    task_id: str
    tool_calls: list
    step_count: int
    status: str


async def run_target(
    task: TargetTask,
    config: AgentConfig,
    *,
    tools: ToolEnvironment,
    settings: Settings | None = None,
    model=None,
) -> TargetRunResult:
    settings = settings or load_settings()
    start = perf_counter()
    run_id = uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    effective = {
        "num_ctx": settings.ollama_num_ctx,
        "num_predict": config.num_predict,
        "temperature": settings.ollama_temperature,
        "seed": settings.ollama_seed,
        "reasoning": config.reasoning,
    }
    # Hash the actual data before exposing any evidence. No silent seed-file fallback.
    preflight_error = None
    try:
        data_hash = snapshot(tools.engine)
    except SQLAlchemyError:
        data_hash = None
        preflight_error = "data_source_unavailable"
    if model is None:
        model = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_host,
            client_kwargs={"timeout": min(settings.ollama_timeout_seconds, config.timeout_seconds)},
            **effective,
        )
        model = model.bind_tools(tools.definitions(config))
    observations = []
    messages = [SystemMessage(content=config.system_prompt), HumanMessage(content=task.prompt)]
    state: TargetState = {
        "messages": messages,
        "task_id": task.task_id,
        "tool_calls": [],
        "step_count": 0,
        "status": "running",
    }
    answer = None
    terminal = preflight_error
    repair_used = False
    failures = {}
    token_totals = {"input_tokens": 0, "output_tokens": 0}
    token_known = {"input_tokens": True, "output_tokens": True}

    def budget():
        if perf_counter() - start >= config.timeout_seconds:
            return "timeout"
        if state["step_count"] >= config.max_steps:
            return "max_steps"
        return None

    async def llm_node(current):
        nonlocal terminal
        if terminal or (terminal := budget()):
            return current
        state["step_count"] += 1
        try:
            remaining = config.timeout_seconds - (perf_counter() - start)
            response = await asyncio.wait_for(
                model.ainvoke(messages), timeout=max(0.001, remaining)
            )
        except (TimeoutError, asyncio.TimeoutError):
            terminal = "timeout"
            return current
        except Exception:
            terminal = "model_unavailable"
            return current
        messages.append(response)
        usage = response.usage_metadata or {}
        for name in token_totals:
            if usage.get(name) is None:
                token_known[name] = False
            else:
                token_totals[name] += usage[name]
        if response.response_metadata.get("done_reason") == "length":
            terminal = "truncated_generation"
        elif response.invalid_tool_calls:
            terminal = "invalid_tool_call"
        return {**current, "messages": messages, "step_count": state["step_count"]}

    async def tool_node(current):
        nonlocal terminal
        calls = messages[-1].tool_calls
        for call in calls:
            reason = None
            if perf_counter() - start >= config.timeout_seconds:
                reason = "timeout"
            elif len(observations) >= config.max_tool_calls:
                reason = "max_tool_calls"
            key = json.dumps([call["name"], call["args"]], sort_keys=True)
            if failures.get(key, 0) >= 1 + config.max_tool_retries:
                reason = reason or "max_tool_retries"
            if terminal or reason:
                terminal = terminal or reason
                messages.append(
                    ToolMessage(content=json.dumps({"error": terminal}), tool_call_id=call["id"])
                )
                continue
            # SQL has finite I/O timeouts; a timed-out worker can finish a read, never a write.
            try:
                remaining = config.timeout_seconds - (perf_counter() - start)
                observation = await asyncio.wait_for(
                    asyncio.to_thread(tools.execute, call["name"], call["args"], call["id"]),
                    max(0.001, remaining),
                )
            except TimeoutError:
                terminal = "timeout"
                messages.append(ToolMessage(content='{"error":"timeout"}', tool_call_id=call["id"]))
                continue
            observations.append(observation)
            if not observation.ok:
                failures[key] = failures.get(key, 0) + 1
            messages.append(
                ToolMessage(
                    content=observation.model_dump_json(),
                    tool_call_id=call["id"],
                    name=call["name"],
                )
            )
        return {**current, "messages": messages, "tool_calls": observations}

    async def validate_node(current):
        nonlocal answer, terminal, repair_used
        try:
            content = messages[-1].content
            if not isinstance(content, str):
                raise ValueError("nontext answer")
            answer = TargetAnswer.model_validate_json(content)
            available = {o.observation_id for o in observations}
            available.update(s for o in observations for s in o.source_ids)
            if not set(answer.evidence_ids) <= available or not answer.evidence_ids:
                raise ValueError("unsupported evidence")
            terminal = "completed"
        except (ValidationError, ValueError):
            answer = None
            if repair_used:
                terminal = "invalid_answer"
            else:
                repair_used = True
                messages.append(
                    HumanMessage(
                        content=(
                            "Return ONLY valid JSON with answer (string), facts (object), "
                            "evidence_ids (nonempty array). Cite only source_ids or "
                            "observation_id values already returned by tools. Correct the "
                            "answer format using the existing evidence. "
                            "Do not call more tools. /no_think"
                        )
                    )
                )
        return current

    def route_llm(current):
        nonlocal terminal
        if terminal:
            return END
        if isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
            if repair_used:
                for call in messages[-1].tool_calls:
                    messages.append(
                        ToolMessage(
                            content='{"error":"tools_disabled_during_answer_repair"}',
                            tool_call_id=call["id"],
                        )
                    )
                terminal = "invalid_answer"
                return END
            return "tools"
        return "validate"

    builder = StateGraph(TargetState)
    builder.add_node("model", llm_node)
    builder.add_node("tools", tool_node)
    builder.add_node("validate", validate_node)
    builder.add_edge(START, "model")
    builder.add_conditional_edges("model", route_llm)
    builder.add_conditional_edges("tools", lambda _: END if terminal else "model")
    builder.add_conditional_edges("validate", lambda _: END if terminal else "model")
    try:
        await builder.compile().ainvoke(state, config={"recursion_limit": config.max_steps * 3 + 5})
    except Exception:
        terminal = terminal or "execution_error"
    if not token_totals["input_tokens"]:
        token_known["input_tokens"] = False
    if not token_totals["output_tokens"]:
        token_known["output_tokens"] = False
    return TargetRunResult(
        run_id=run_id,
        task_id=task.task_id,
        prompt=task.prompt,
        started_at=started_at,
        config_hash=config.content_hash(),
        data_hash=data_hash,
        model=settings.ollama_model,
        model_settings=effective,
        status="completed" if terminal == "completed" else "failed",
        terminal_reason=terminal or "execution_error",
        answer=answer,
        observations=observations,
        messages=[
            {
                "type": m.type,
                "content": m.content,
                **({"tool_calls": m.tool_calls} if isinstance(m, AIMessage) else {}),
                **({"tool_call_id": m.tool_call_id} if isinstance(m, ToolMessage) else {}),
            }
            for m in messages
        ],
        model_calls=state["step_count"],
        input_tokens=token_totals["input_tokens"] if token_known["input_tokens"] else None,
        output_tokens=token_totals["output_tokens"] if token_known["output_tokens"] else None,
        latency_ms=round((perf_counter() - start) * 1000, 3),
        injected_failure=tools.injected,
    )
