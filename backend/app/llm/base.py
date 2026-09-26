"""Provider-neutral contract every LLM adapter implements."""

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

Role = Literal["system", "user", "assistant"]
ErrorKind = Literal["timeout", "rate_limit", "server", "client", "auth", "parse", "unavailable"]
RETRYABLE: frozenset[str] = frozenset({"timeout", "rate_limit", "server"})


@dataclass(frozen=True)
class Message:
    role: Role
    content: str


@dataclass
class LLMResponse:
    content: dict[str, Any]
    provider: str
    vendor: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0


class ProviderError(Exception):
    def __init__(self, kind: ErrorKind, message: str = "") -> None:
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind

    @property
    def retryable(self) -> bool:
        return self.kind in RETRYABLE


class LLMProvider(Protocol):
    name: str
    vendor: str
    model: str

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse: ...


def split_system(messages: list[Message]) -> tuple[str, list[Message]]:
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    return system, [m for m in messages if m.role != "system"]


def parse_json(text: str) -> dict[str, Any]:
    """Parse a JSON object, tolerating a markdown fence; anything else is a parse failure."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{") :] if "{" in cleaned else cleaned
    try:
        value = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError) as error:
        raise ProviderError("parse", f"invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise ProviderError("parse", "expected a JSON object")
    return value


def status_kind(status: int) -> ErrorKind:
    if status == 429:
        return "rate_limit"
    if status in (401, 403):
        return "auth"
    if status >= 500 or status == 408:
        return "server" if status != 408 else "timeout"
    return "client"
