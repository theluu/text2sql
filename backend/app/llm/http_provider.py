"""Shared plumbing for providers called over plain HTTP (OpenAI, Gemini, Ollama)."""

import time
from typing import Any

import httpx

from app.llm.base import ProviderError, status_kind


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_s: float,
) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    try:
        response = await client.post(url, json=body, headers=headers, timeout=timeout_s)
    except httpx.TimeoutException as error:
        raise ProviderError("timeout", str(error)) from error
    except httpx.HTTPError as error:
        raise ProviderError("unavailable", str(error)) from error
    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        raise ProviderError(status_kind(response.status_code), response.text[:200])
    try:
        data: dict[str, Any] = response.json()
    except ValueError as error:
        raise ProviderError("parse", "non-JSON response body") from error
    return data, latency
