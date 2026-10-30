"""Observability wrapper that does not alter the frozen A0 implementation files."""

from dataclasses import dataclass
from pathlib import Path

from langchain_ollama import ChatOllama

from tracefix.common.config import Settings
from tracefix.target_agent.cli import save_run
from tracefix.target_agent.config import AgentConfig
from tracefix.target_agent.graph import run_target
from tracefix.target_agent.schemas import TargetRunResult, TargetTask
from tracefix.target_agent.tools import ToolEnvironment
from tracefix.telemetry.index import save_target_run
from tracefix.telemetry.recording import TelemetrySession, target_metadata
from tracefix.telemetry.redaction import sanitize


class ObservedModel:
    def __init__(self, bound_model, callback):
        self.bound_model = bound_model
        self.callback = callback

    async def ainvoke(self, messages):
        if self.callback is None:
            return await self.bound_model.ainvoke(messages)
        return await self.bound_model.ainvoke(
            messages, config={"callbacks": [self.callback], "run_name": "generate-target-response"}
        )


class ObservedTools:
    def __init__(self, tools: ToolEnvironment, telemetry: TelemetrySession):
        self.tools = tools
        self.telemetry = telemetry
        self.engine = tools.engine
        self.executions = []

    @property
    def injected(self):
        return self.tools.injected

    def definitions(self, config):
        return self.tools.definitions(config)

    def execute(self, name, arguments, call_id):
        self.executions.append(call_id)
        observation = None
        tool_failed = False
        try:
            with self.telemetry.tool(name, arguments, call_id) as span:
                try:
                    observation = self.tools.execute(name, arguments, call_id)
                except Exception:
                    tool_failed = True
                    if span is not None:
                        try:
                            span.update(
                                level="ERROR",
                                status_message="tool_execution_error",
                                output={"ok": False, "error": "tool_execution_error"},
                            )
                        except Exception:
                            self.telemetry.status = "unavailable"
                    raise
                if span is not None:
                    span.update(
                        output=sanitize(
                            observation.model_dump(mode="json"), secrets=self.telemetry.secrets
                        ),
                        metadata={
                            "local_observation_id": observation.observation_id,
                            "call_id": call_id,
                            "ok": str(observation.ok).lower(),
                        },
                        level="DEFAULT" if observation.ok else "ERROR",
                        status_message=observation.error,
                    )
                return observation
        except Exception:
            if not tool_failed:
                self.telemetry.status = "unavailable"
            if observation is not None:
                return observation
            raise


@dataclass(frozen=True)
class ObservedRun:
    result: TargetRunResult
    trace_id: str | None
    telemetry_status: str
    run_file: Path


async def run_observed(
    task: TargetTask,
    config: AgentConfig,
    *,
    tools: ToolEnvironment,
    settings: Settings,
    metadata: dict,
    output: Path,
    telemetry: TelemetrySession,
    model=None,
) -> ObservedRun:
    if hasattr(telemetry, "begin_run"):
        telemetry.begin_run()
    model_id = settings.ollama_model
    if model is None:
        model = ChatOllama(
            model=model_id,
            base_url=settings.ollama_host,
            client_kwargs={"timeout": min(settings.ollama_timeout_seconds, config.timeout_seconds)},
            num_ctx=settings.ollama_num_ctx,
            num_predict=config.num_predict,
            temperature=settings.ollama_temperature,
            seed=settings.ollama_seed,
            reasoning=config.reasoning,
        ).bind_tools(tools.definitions(config))
    try:
        callback = telemetry.callback()
    except Exception:
        telemetry.status = "unavailable"
        callback = None
    wrapped_model = ObservedModel(model, callback)
    wrapped_tools = ObservedTools(tools, telemetry)
    trace_id = telemetry.trace_id()
    identity = target_metadata(metadata, task_id=task.task_id, model_id=model_id)
    with telemetry.root("tracefix-target-a", trace_id, identity, {"prompt": task.prompt}) as span:
        result = await run_target(
            task, config, tools=wrapped_tools, settings=settings, model=wrapped_model
        )
        if span is not None:
            try:
                span.update(
                    output=sanitize(
                        {
                            "answer": result.answer.model_dump() if result.answer else None,
                            "terminal_reason": result.terminal_reason,
                        },
                        secrets=telemetry.secrets,
                    ),
                    metadata={
                        **identity,
                        "run_id": result.run_id,
                        "terminal_reason": result.terminal_reason,
                        "outcome": result.status,
                        "config_hash": result.config_hash,
                        "data_hash": result.data_hash or "unavailable",
                        "model_settings": result.model_settings,
                        "expected_model_calls": str(result.model_calls),
                        "expected_tool_calls": str(len(wrapped_tools.executions)),
                        "returned_tool_calls": str(len(result.observations)),
                    },
                    level="DEFAULT" if result.status == "completed" else "ERROR",
                    status_message=None if result.status == "completed" else result.terminal_reason,
                )
            except Exception:
                telemetry.status = "unavailable"
    run_file = save_run(result, output)
    save_target_run(
        tools.engine,
        result,
        metadata,
        trace_id,
        telemetry.status,
        executed_tool_calls=len(wrapped_tools.executions),
    )
    if hasattr(telemetry, "register_run"):
        telemetry.register_run(tools.engine, result.run_id)
    return ObservedRun(result, trace_id, telemetry.status, run_file)
