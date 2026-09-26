import time
from typing import Any

import anthropic

from app.llm.base import ErrorKind, LLMResponse, Message, ProviderError, parse_json, split_system
from app.llm.pricing import cost_usd


class AnthropicProvider:
    vendor = "anthropic"

    def __init__(
        self, api_key: str, model: str, *, client: anthropic.AsyncAnthropic | None = None
    ) -> None:
        self.name = "anthropic"
        self.model = model
        # The router owns retries/backoff so failover stays within its time budget.
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key, max_retries=0)

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse:
        system, turns = split_system(messages)
        started = time.perf_counter()
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=8000,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in turns],
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": schema},
                },
                timeout=timeout_s,
            )
        except anthropic.APITimeoutError as error:
            raise ProviderError("timeout", str(error)) from error
        except anthropic.RateLimitError as error:
            raise ProviderError("rate_limit", str(error)) from error
        except anthropic.AuthenticationError as error:
            raise ProviderError("auth", str(error)) from error
        except anthropic.APIStatusError as error:
            kind: ErrorKind = "server" if error.status_code >= 500 else "client"
            raise ProviderError(kind, f"{error.status_code} {error.message}") from error
        except anthropic.APIConnectionError as error:
            raise ProviderError("unavailable", str(error)) from error
        if response.stop_reason == "refusal":
            raise ProviderError("client", "model refused")
        text = next((b.text for b in response.content if b.type == "text"), "")
        content = parse_json(text)
        usage = response.usage
        return LLMResponse(
            content=content,
            provider=self.name,
            vendor=self.vendor,
            model=self.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            cost_usd=cost_usd(self.model, usage.input_tokens, usage.output_tokens),
        )
