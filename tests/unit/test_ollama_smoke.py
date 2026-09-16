import pytest
from ollama import ChatResponse
from pydantic import ValidationError

from tracefix.common.config import Settings
from tracefix.common.ollama_smoke import run_smoke


class FakeClient:
    def __init__(
        self, *, tool_name="add_numbers", structured='{"operation":"addition","result":42}'
    ):
        self.calls = []
        messages = [
            {"role": "assistant", "content": "ready"},
            {
                "role": "assistant",
                "tool_calls": [{"function": {"name": tool_name, "arguments": {"a": 19, "b": 23}}}],
            },
            {"role": "assistant", "content": "The result is 42."},
            {"role": "assistant", "content": structured},
        ]
        self.responses = iter(
            ChatResponse(
                model="fake",
                message=message,
                done=True,
                done_reason="stop",
                prompt_eval_count=10,
                eval_count=5,
            )
            for message in messages
        )

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


def test_tool_result_is_returned_and_model_configuration_is_recorded():
    client = FakeClient()
    result = run_smoke(Settings(_env_file=None), "fake", client=client)
    assert result["status"] == "passed"
    assert len(result["calls"]) == 4
    assert result["options"]["num_ctx"] == 8192
    assert client.calls[2]["messages"][-1]["content"] == "42"
    assert all(call["think"] is False for call in client.calls)
    assert all(call["options"] == result["options"] for call in client.calls)


def test_unexpected_tool_is_rejected():
    with pytest.raises(RuntimeError, match="Expected one"):
        run_smoke(Settings(_env_file=None), "fake", client=FakeClient(tool_name="shell"))


def test_incorrect_structured_result_is_rejected():
    with pytest.raises(RuntimeError, match="did not equal 42"):
        run_smoke(
            Settings(_env_file=None),
            "fake",
            client=FakeClient(
                structured='{"operation":"addition","result":99}',
            ),
        )


def test_malformed_json_is_rejected():
    with pytest.raises(ValidationError):
        run_smoke(Settings(_env_file=None), "fake", client=FakeClient(structured="not json"))


def test_truncated_generation_is_not_reported_as_success():
    client = FakeClient()
    client.responses = iter(
        [
            ChatResponse(
                model="fake",
                message={"role": "assistant", "content": "partial"},
                done=True,
                done_reason="length",
            )
        ]
    )
    with pytest.raises(RuntimeError, match="token budget"):
        run_smoke(Settings(_env_file=None), "fake", client=client)
