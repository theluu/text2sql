from typing import Any

import httpx

from app.llm.base import LLMResponse, Message, ProviderError, parse_json, split_system
from app.llm.http_provider import post_json
from app.llm.pricing import cost_usd


class GeminiProvider:
    vendor = "google"

    def __init__(
        self, api_key: str, model: str, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self.name = "gemini"
        self.model = model
        self._key = api_key
        self._client = client or httpx.AsyncClient()

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse:
        system, turns = split_system(messages)
        body: dict[str, Any] = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in turns
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        data, latency = await post_json(
            self._client,
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            headers={"x-goog-api-key": self._key},
            body=body,
            timeout_s=timeout_s,
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError, TypeError) as error:
            raise ProviderError("parse", "unexpected response shape") from error
        usage = data.get("usageMetadata") or {}
        tokens_in = int(usage.get("promptTokenCount", 0))
        tokens_out = int(usage.get("candidatesTokenCount", 0))
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
