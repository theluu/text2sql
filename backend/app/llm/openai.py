from typing import Any

import httpx

from app.llm.base import LLMResponse, Message, ProviderError, parse_json
from app.llm.http_provider import post_json
from app.llm.pricing import cost_usd

REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")


class OpenAIProvider:
    vendor = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        reasoning_effort: str | None = "low",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.name = "openai"
        self.model = model
        self._key = api_key
        self._effort = reasoning_effort
        self._client = client or httpx.AsyncClient()

    def _reasoning_effort(self, schema_name: str) -> str | None:
        """SQL generation gets the configured effort; short grading/screening calls stay minimal."""
        if not self.model.startswith(REASONING_PREFIXES) or not self._effort:
            return None
        return self._effort if schema_name == "sql_candidate" else "minimal"

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        }
        if effort := self._reasoning_effort(schema_name):
            body["reasoning_effort"] = effort
        data, latency = await post_json(
            self._client,
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            body=body,
            timeout_s=timeout_s,
        )
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("parse", "unexpected response shape") from error
        usage = data.get("usage") or {}
        tokens_in, tokens_out = (
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )
        return LLMResponse(
            content=parse_json(text),
            provider=self.name,
            vendor=self.vendor,
            model=self.model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            latency_ms=latency,
            cost_usd=cost_usd(self.model, tokens_in, tokens_out),
        )
