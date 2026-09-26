from typing import Any

import httpx

from app.llm.base import LLMResponse, Message, ProviderError, parse_json
from app.llm.http_provider import post_json


class OllamaProvider:
    vendor = "ollama"

    def __init__(
        self, base_url: str, model: str, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.name = "ollama"
        self.model = model
        self._url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient()

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse:
        data, latency = await post_json(
            self._client,
            f"{self._url}/api/chat",
            headers={},
            body={
                "model": self.model,
                "messages": [{"role": m.role, "content": m.content} for m in messages],
                "stream": False,
                "format": schema,
                "options": {"temperature": 0},
            },
            timeout_s=timeout_s,
        )
        try:
            text = data["message"]["content"]
        except (KeyError, TypeError) as error:
            raise ProviderError("parse", "unexpected response shape") from error
        return LLMResponse(
            content=parse_json(text),
            provider=self.name,
            vendor=self.vendor,
            model=self.model,
            input_tokens=int(data.get("prompt_eval_count", 0)),
            output_tokens=int(data.get("eval_count", 0)),
            latency_ms=latency,
        )
