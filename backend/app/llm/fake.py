"""Scripted provider for tests and cassette replay."""

from collections.abc import Callable
from typing import Any

from app.llm.base import LLMResponse, Message, ProviderError

Step = dict[str, Any] | ProviderError | Callable[[list[Message], str], dict[str, Any]]


class FakeLLMProvider:
    """Plays `script` in order (the last step repeats). A callable step sees the messages and
    schema name, so one fake can answer generate/judge/classify calls differently."""

    def __init__(self, name: str = "fake", vendor: str = "fake", script: list[Step] | None = None,
                 model: str = "fake-1") -> None:  # fmt: skip
        self.name = name
        self.vendor = vendor
        self.model = model
        self.script: list[Step] = list(script or [{}])
        self.calls: list[tuple[str, list[Message]]] = []

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse:
        index = min(len(self.calls), len(self.script) - 1)
        self.calls.append((schema_name, messages))
        step = self.script[index]
        if isinstance(step, ProviderError):
            raise step
        content = step(messages, schema_name) if callable(step) else step
        return LLMResponse(
            content=dict(content), provider=self.name, vendor=self.vendor, model=self.model,
            input_tokens=100, output_tokens=50, latency_ms=5, cost_usd=0.0001,
        )  # fmt: skip
