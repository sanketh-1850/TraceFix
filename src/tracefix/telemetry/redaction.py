"""Bound and redact telemetry before it leaves the process."""

import re
from typing import Any

from pydantic import BaseModel, SecretStr

SENSITIVE_KEY = re.compile(
    r"password|secret|authorization|api.?key|public.?key|access.?token|cookie|reasoning|thinking",
    re.I,
)
BEARER = re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/-]+")
URL_AUTH = re.compile(r"(https?://)[^/@\s]+@", re.I)
ASSIGNMENT = re.compile(r"(?i)\b(password|secret|api[_-]?key|token)\s*[:=]\s*[^\s,;]+")


def sanitize(value: Any, *, secrets: tuple[str, ...] = (), limit: int = 4000) -> Any:
    if isinstance(value, SecretStr):
        return "[REDACTED]"
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            str(key): (
                "[REDACTED]"
                if SENSITIVE_KEY.search(str(key))
                else sanitize(item, secrets=secrets, limit=limit)
            )
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [sanitize(item, secrets=secrets, limit=limit) for item in value[:100]]
    if isinstance(value, str):
        value = BEARER.sub(r"\1[REDACTED]", value)
        value = URL_AUTH.sub(r"\1[REDACTED]@", value)
        value = ASSIGNMENT.sub(lambda match: match.group(1) + "=[REDACTED]", value)
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value[:limit] + ("...[truncated]" if len(value) > limit else "")
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return sanitize(str(value), secrets=secrets, limit=limit)
