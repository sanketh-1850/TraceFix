"""Langfuse recording around frozen target and future Judge executions."""

from contextlib import ExitStack, contextmanager
from uuid import uuid4

from tracefix.common.config import Settings
from tracefix.telemetry.redaction import sanitize


def target_metadata(metadata: dict, *, task_id: str, model_id: str) -> dict[str, str]:
    result = {
        "kind": "target",
        "target_id": str(metadata["target_id"]),
        "task_id": task_id,
        "agent_version_id": str(metadata["agent_version_id"]),
        "model_id": model_id,
        "dataset_version": str(metadata["dataset_version"]),
    }
    for key in ("benchmark_snapshot_id", "evaluator_version", "split"):
        if metadata.get(key):
            result[key] = str(metadata[key])
    return result


def judge_metadata(
    *,
    judge_run_id: str,
    mode: str,
    target_id: str,
    source_target_run_id: str,
    manifest_version: str,
) -> dict[str, str]:
    if mode not in {"generic", "specialized"}:
        raise ValueError("Judge mode must be generic or specialized")
    return {
        "kind": "judge",
        "judge_run_id": judge_run_id,
        "mode": mode,
        "target_id": target_id,
        "source_target_run_id": source_target_run_id,
        "manifest_version": manifest_version,
    }


class TelemetrySession:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = None
        self.status = "disabled"
        self._runs = []
        self._export_failed = False
        self.secrets = (
            settings.db_password.get_secret_value(),
            settings.langfuse_secret_key.get_secret_value(),
        )
        if not settings.langfuse_enabled:
            return
        if not settings.langfuse_public_key or not settings.langfuse_secret_key.get_secret_value():
            self.status = "unavailable"
            return
        try:
            from langfuse import Langfuse

            self.client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key.get_secret_value(),
                base_url=settings.langfuse_host,
                timeout=10,
                environment=settings.langfuse_environment,
                mask=lambda data, **kwargs: sanitize(data, secrets=self.secrets),
            )
            self.status = "pending"
        except Exception:
            self.status = "unavailable"

    def trace_id(self) -> str | None:
        return uuid4().hex if self.client is not None else None

    def begin_run(self):
        if self.client is not None:
            self.status = "pending"

    def register_run(self, engine, run_id):
        self._runs.append((engine, run_id))

    def callback(self):
        if self.client is None:
            return None
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(public_key=self.settings.langfuse_public_key)

    @contextmanager
    def root(self, name: str, trace_id: str | None, metadata: dict, input_data: dict):
        if self.client is None:
            yield None
            return
        from langfuse import propagate_attributes

        stack = ExitStack()
        try:
            span = stack.enter_context(
                self.client.start_as_current_observation(
                    as_type="span",
                    name=name,
                    trace_context={"trace_id": trace_id},
                    input=sanitize(input_data, secrets=self.secrets),
                    metadata=metadata,
                )
            )
            stack.enter_context(
                propagate_attributes(
                    metadata=metadata,
                    environment=self.settings.langfuse_environment,
                    trace_name=name,
                )
            )
        except Exception:
            self.status = "unavailable"
            self._close(stack)
            yield None
            return
        try:
            yield span
        finally:
            self._close(stack)

    @contextmanager
    def tool(self, name: str, args: dict, call_id: str):
        if self.client is None:
            yield None
            return
        stack = ExitStack()
        try:
            span = stack.enter_context(
                self.client.start_as_current_observation(
                    as_type="tool",
                    name=name,
                    input=sanitize(args, secrets=self.secrets),
                    metadata={"call_id": call_id},
                )
            )
        except Exception:
            self.status = "unavailable"
            self._close(stack)
            yield None
            return
        try:
            yield span
        finally:
            self._close(stack)

    def _close(self, stack):
        try:
            stack.close()
        except Exception:
            self.status = "unavailable"

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception:
                self.status = "unavailable"
                self._export_failed = True

    def shutdown(self) -> None:
        if self.client is not None:
            try:
                self.client.shutdown()
            except Exception:
                self.status = "unavailable"
                self._export_failed = True
        if self._export_failed:
            from tracefix.telemetry.index import get_target_run, set_telemetry_status

            for engine, run_id in self._runs:
                if get_target_run(engine, run_id).telemetry_status != "verified":
                    set_telemetry_status(engine, run_id, "unavailable")

    def finalize(self):
        self.flush()
        self.shutdown()


class JudgeRecorder:
    """Stage-independent tracing surface; the Judge graph will use this in Epic 4."""

    def __init__(self, session: TelemetrySession):
        self.session = session

    @contextmanager
    def run(
        self,
        *,
        judge_run_id: str,
        mode: str,
        target_id: str,
        source_target_run_id: str,
        manifest_version: str,
    ):
        metadata = judge_metadata(
            judge_run_id=judge_run_id,
            mode=mode,
            target_id=target_id,
            source_target_run_id=source_target_run_id,
            manifest_version=manifest_version,
        )
        trace_id = self.session.trace_id()
        with self.session.root(
            "tracefix-judge",
            trace_id,
            metadata,
            {"source_target_run_id": source_target_run_id, "mode": mode},
        ) as span:
            yield trace_id, span

    @contextmanager
    def diagnostic_tool(self, name: str, arguments: dict, call_id: str):
        with self.session.tool(name, arguments, call_id) as span:
            yield span

    def finish(
        self,
        span,
        *,
        diagnosis: dict,
        fallback_used: bool,
        tokens: int | None,
        tool_calls: int,
        latency_ms: float,
    ) -> None:
        if span is not None:
            try:
                span.update(
                    output=sanitize(diagnosis, secrets=self.session.secrets),
                    metadata={
                        "fallback_used": str(fallback_used).lower(),
                        "tokens": str(tokens) if tokens is not None else "unknown",
                        "diagnostic_tool_calls": str(tool_calls),
                        "latency_ms": str(latency_ms),
                    },
                )
            except Exception:
                self.session.status = "unavailable"
