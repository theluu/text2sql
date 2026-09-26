import json
from typing import Any

import anthropic
import httpx
import httpx2
import pytest

from app.llm.anthropic import AnthropicProvider
from app.llm.base import Message, ProviderError
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai import OpenAIProvider

SCHEMA = {
    "type": "object",
    "properties": {"sql": {"type": "string"}},
    "required": ["sql"],
    "additionalProperties": False,
}
MESSAGES = [Message("system", "be terse"), Message("user", "count orders")]
ANSWER = {"sql": "SELECT count(*) FROM orders"}


def _mock(status: int, body: Any, seen: list[httpx.Request]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_openai_adapter_maps_response_and_usage() -> None:
    seen: list[httpx.Request] = []
    body = {
        "choices": [{"message": {"content": json.dumps(ANSWER)}}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 30},
    }
    provider = OpenAIProvider("k", "gpt-5-mini", client=_mock(200, body, seen))
    response = await provider.complete(MESSAGES, schema=SCHEMA, schema_name="gen", timeout_s=5)
    assert response.content == ANSWER
    assert (response.provider, response.vendor, response.model) == (
        "openai",
        "openai",
        "gpt-5-mini",
    )
    assert (response.input_tokens, response.output_tokens) == (120, 30)
    assert response.cost_usd > 0
    sent = json.loads(seen[0].content)
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert seen[0].headers["authorization"] == "Bearer k"


async def test_gemini_adapter_splits_system_prompt() -> None:
    seen: list[httpx.Request] = []
    body = {
        "candidates": [{"content": {"parts": [{"text": json.dumps(ANSWER)}]}}],
        "usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 20},
    }
    provider = GeminiProvider("k", "gemini-2.5-flash", client=_mock(200, body, seen))
    response = await provider.complete(MESSAGES, schema=SCHEMA, schema_name="gen", timeout_s=5)
    assert response.content == ANSWER and response.vendor == "google"
    sent = json.loads(seen[0].content)
    assert sent["systemInstruction"]["parts"][0]["text"] == "be terse"
    assert [c["role"] for c in sent["contents"]] == ["user"]
    assert sent["generationConfig"]["responseJsonSchema"] == SCHEMA


async def test_ollama_adapter_passes_schema_as_format() -> None:
    seen: list[httpx.Request] = []
    body = {"message": {"content": json.dumps(ANSWER)}, "prompt_eval_count": 9, "eval_count": 4}
    provider = OllamaProvider("http://ollama:11434", "qwen", client=_mock(200, body, seen))
    response = await provider.complete(MESSAGES, schema=SCHEMA, schema_name="gen", timeout_s=5)
    assert response.content == ANSWER and response.cost_usd == 0
    assert json.loads(seen[0].content)["format"] == SCHEMA


@pytest.mark.parametrize(
    ("status", "kind", "retryable"),
    [
        (429, "rate_limit", True),
        (503, "server", True),
        (400, "client", False),
        (401, "auth", False),
    ],
)
async def test_http_errors_are_classified(status: int, kind: str, retryable: bool) -> None:
    provider = OpenAIProvider("k", "gpt-5-mini", client=_mock(status, {"error": "x"}, []))
    with pytest.raises(ProviderError) as caught:
        await provider.complete(MESSAGES, schema=SCHEMA, schema_name="gen", timeout_s=5)
    assert caught.value.kind == kind and caught.value.retryable is retryable


async def test_non_json_content_is_a_parse_failure() -> None:
    body = {"choices": [{"message": {"content": "Sure! Here is SQL: SELECT 1"}}], "usage": {}}
    provider = OpenAIProvider("k", "gpt-5-mini", client=_mock(200, body, []))
    with pytest.raises(ProviderError) as caught:
        await provider.complete(MESSAGES, schema=SCHEMA, schema_name="gen", timeout_s=5)
    assert caught.value.kind == "parse"


def _anthropic(status: int, body: Any, seen: list[httpx2.Request]) -> AnthropicProvider:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status, json=body)

    client = anthropic.AsyncAnthropic(
        api_key="k",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicProvider("k", "claude-sonnet-5", client=client)


async def test_anthropic_adapter_uses_structured_outputs() -> None:
    seen: list[httpx2.Request] = []
    body = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": json.dumps(ANSWER)}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 200, "output_tokens": 40},
    }
    provider = _anthropic(200, body, seen)
    response = await provider.complete(MESSAGES, schema=SCHEMA, schema_name="gen", timeout_s=5)
    assert response.content == ANSWER
    assert (response.input_tokens, response.output_tokens) == (200, 40)
    assert response.cost_usd == pytest.approx((200 * 2 + 40 * 10) / 1_000_000)
    sent = json.loads(seen[0].content)
    assert sent["system"] == "be terse"
    assert sent["output_config"]["format"] == {"type": "json_schema", "schema": SCHEMA}
    assert [m["role"] for m in sent["messages"]] == ["user"]


@pytest.mark.parametrize(
    ("status", "kind"), [(429, "rate_limit"), (529, "server"), (400, "client")]
)
async def test_anthropic_errors_are_classified(status: int, kind: str) -> None:
    body = {"type": "error", "error": {"type": "x", "message": "boom"}}
    provider = _anthropic(status, body, [])
    with pytest.raises(ProviderError) as caught:
        await provider.complete(MESSAGES, schema=SCHEMA, schema_name="gen", timeout_s=5)
    assert caught.value.kind == kind
