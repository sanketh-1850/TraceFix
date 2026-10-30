"""Load local settings without exposing credentials in logs or URLs."""

import os
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)

    db_user: str = "root"
    db_password: SecretStr = SecretStr("")
    db_name: str = Field(default="TraceFix_DB", pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    db_host: str = "127.0.0.1"
    db_port: int = Field(default=3306, ge=1, le=65535)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    ollama_judge_model: str = "qwen3:8b"
    ollama_num_ctx: int = Field(default=8192, ge=1024)
    ollama_num_predict: int = Field(default=512, ge=64, le=4096)
    ollama_temperature: float = Field(default=0, ge=0, le=2)
    ollama_seed: int = 42
    ollama_timeout_seconds: float = Field(default=300, gt=0)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_environment: str = "development"

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings
    ):
        def with_langfuse_url(source):
            def read():
                raw = getattr(source, "env_vars", getattr(source, "init_kwargs", {}))
                values = {str(key).lower(): value for key, value in raw.items()}
                base = values.get("langfuse_base_url")
                host = values.get("langfuse_host")
                if base and host and base.rstrip("/") != host.rstrip("/"):
                    raise ValueError("Conflicting LANGFUSE_BASE_URL and LANGFUSE_HOST")
                data = source()
                for key in list(data):
                    if key.lower() in {"langfuse_base_url", "langfuse_host"}:
                        data.pop(key)
                if base or host:
                    data["langfuse_host"] = (base or host).rstrip("/")
                return data

            return read

        return (
            with_langfuse_url(init_settings),
            with_langfuse_url(env_settings),
            with_langfuse_url(dotenv_settings),
            file_secret_settings,
        )

    def database_url(self, *, include_database: bool = True) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name if include_database else None,
            query={"charset": "utf8mb4"},
        )


def load_settings(env_file: str | Path | None = None) -> Settings:
    """OS environment takes precedence; TRACEFIX_ENV_FILE selects an alternate file."""
    path = env_file or os.environ.get("TRACEFIX_ENV_FILE") or PROJECT_ROOT / "server.env"
    return Settings(_env_file=path, _env_file_encoding="utf-8")
