import hashlib
import json
from pathlib import Path

from pydantic import Field

from tracefix.common.config import PROJECT_ROOT
from tracefix.target_agent.schemas import StrictModel

DATA_ROOT = PROJECT_ROOT / "data"
DEFAULT_CONFIG = PROJECT_ROOT / "configs/agents/order_support.json"


class AgentConfig(StrictModel):
    version: str
    system_prompt: str
    tool_descriptions: dict[str, str]
    max_steps: int = Field(default=10, ge=1, le=50)
    max_tool_calls: int = Field(default=12, ge=1, le=100)
    max_tool_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: float = Field(default=300, gt=0)
    num_predict: int = Field(default=2048, ge=64, le=4096)
    reasoning: bool = True

    def content_hash(self) -> str:
        return digest(self.model_dump())


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def load_agent_config(path: Path = DEFAULT_CONFIG) -> AgentConfig:
    return AgentConfig.model_validate_json(path.read_text(encoding="utf-8"))
