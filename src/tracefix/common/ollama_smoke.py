"""Manual live diagnostics; default unit tests use a fake client."""

import argparse
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Literal

from ollama import Client
from pydantic import BaseModel, ConfigDict, StrictInt

from tracefix.common.config import Settings, load_settings
from tracefix.common.logging import configure_logging


class AdditionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: StrictInt
    b: StrictInt


class ArithmeticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["addition"]
    result: StrictInt


class SmokeCheckError(RuntimeError):
    """A local diagnostic assertion whose message is safe to show to the user."""


ADD_TOOL = {
    "type": "function",
    "function": {
        "name": "add_numbers",
        "description": "Add two integers. Use this tool for the requested addition.",
        "parameters": AdditionArguments.model_json_schema(),
    },
}


def run_smoke(settings: Settings, model: str, *, client=None) -> dict:
    """Check generation, a complete tool round trip, and schema-constrained output."""
    client = client or Client(host=settings.ollama_host, timeout=settings.ollama_timeout_seconds)
    options = {
        "num_ctx": settings.ollama_num_ctx,
        "temperature": settings.ollama_temperature,
        "seed": settings.ollama_seed,
        "num_predict": settings.ollama_num_predict,
    }
    report = {
        "model": model,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "options": options,
        "think": False,
        "calls": [],
    }

    def chat(label, messages, **kwargs):
        start = perf_counter()
        response = client.chat(
            model=model,
            messages=messages,
            options=options,
            think=False,
            stream=False,
            keep_alive=0,
            **kwargs,
        )
        report["calls"].append(
            {
                "check": label,
                "latency_seconds": round(perf_counter() - start, 3),
                "input_tokens": response.prompt_eval_count,
                "output_tokens": response.eval_count,
                "done_reason": response.done_reason,
            }
        )
        if not response.done or response.done_reason == "length":
            raise SmokeCheckError(f"{label}: generation did not finish within the token budget")
        return response

    response = chat("generation", [{"role": "user", "content": "Reply with the word ready."}])
    if not response.message.content or not response.message.content.strip():
        raise SmokeCheckError("Generation returned no text")

    messages = [
        {
            "role": "system",
            "content": (
                "You must use the provided tool for arithmetic. "
                "Make exactly one tool call and no explanation."
            ),
        },
        {"role": "user", "content": "Use add_numbers to add 19 and 23. /no_think"},
    ]
    response = chat("tool_request", messages, tools=[ADD_TOOL])
    calls = response.message.tool_calls or []
    if len(calls) != 1 or calls[0].function.name != "add_numbers":
        raise SmokeCheckError("Expected one add_numbers tool call")
    args = AdditionArguments.model_validate(calls[0].function.arguments)
    if sorted([args.a, args.b]) != [19, 23]:
        raise SmokeCheckError("Model supplied incorrect addition arguments")
    tool_result = args.a + args.b
    messages.append(response.message.model_dump(exclude_none=True))
    messages.append({"role": "tool", "tool_name": "add_numbers", "content": str(tool_result)})
    response = chat("tool_response", messages)
    if not re.search(r"(?<!\d)42(?!\d)", response.message.content or ""):
        raise SmokeCheckError("Final response did not reflect the tool result")

    response = chat(
        "structured_output",
        [{"role": "user", "content": 'Return JSON for 19 + 23: operation="addition", result=42.'}],
        format=ArithmeticResult.model_json_schema(),
    )
    result = ArithmeticResult.model_validate_json(response.message.content or "")
    if result.result != 42:
        raise SmokeCheckError("Structured result did not equal 42")
    report["status"] = "passed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Ollama generation/tool/JSON checks")
    parser.add_argument("--model", help="Override OLLAMA_MODEL")
    parser.add_argument("--all-models", action="store_true", help="Check target and Judge models")
    parser.add_argument("--output", type=Path, default=Path("artifacts/ollama-smoke.json"))
    args = parser.parse_args()
    if args.model and args.all_models:
        parser.error("Choose --model or --all-models")
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        models = (
            [settings.ollama_model, settings.ollama_judge_model]
            if args.all_models
            else [args.model or settings.ollama_model]
        )
        reports = []
        for model in dict.fromkeys(models):
            print(f"Checking {model}...", flush=True)
            reports.append(run_smoke(settings, model))
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
            print(f"{model}: generation, tool calling, and structured JSON passed", flush=True)
        print(f"Run metadata: {args.output}")
        return 0
    except SmokeCheckError as exc:
        logging.error("Ollama check failed: %s", exc)
        return 1
    except Exception as exc:
        logging.error(
            "Ollama check failed (%s). Verify the server, pulled model, and timeout settings.",
            type(exc).__name__,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
