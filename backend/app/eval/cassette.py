"""Record/replay LLM responses so CI evals are deterministic and free.

record: wrap real providers, store every successful response keyed by request hash.
replay: providers are rebuilt from the cassette; unseen requests fail like an outage,
so the router falls through (ultimately to rule-based) exactly as it would in production.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.llm.base import LLMProvider, LLMResponse, Message, ProviderError

CASSETTE_DIR = Path(__file__).resolve().parents[2] / "eval" / "cassettes"


def request_key(provider: str, model: str, schema_name: str, messages: list[Message]) -> str:
    raw = json.dumps(
        [provider, model, schema_name, [(m.role, m.content) for m in messages]], ensure_ascii=False
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class Cassette:
    def __init__(self, path: Path) -> None:
        self.path = path
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        self.providers: dict[str, dict[str, str]] = data.get("providers", {})
        self.entries: dict[str, dict[str, Any]] = data.get("entries", {})
        self.dirty = False

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"providers": self.providers, "entries": dict(sorted(self.entries.items()))}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


class RecordingProvider:
    def __init__(self, inner: LLMProvider, cassette: Cassette) -> None:
        self.inner, self.cassette = inner, cassette
        self.name, self.vendor, self.model = inner.name, inner.vendor, inner.model
        cassette.providers[self.name] = {"vendor": self.vendor, "model": self.model}

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse:
        response = await self.inner.complete(
            messages, schema=schema, schema_name=schema_name, timeout_s=timeout_s
        )
        key = request_key(self.name, self.model, schema_name, messages)
        self.cassette.entries[key] = {
            "content": response.content, "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens, "latency_ms": response.latency_ms,
            "cost_usd": response.cost_usd,
        }  # fmt: skip
        self.cassette.dirty = True
        return response


class ReplayProvider:
    def __init__(self, name: str, vendor: str, model: str, cassette: Cassette) -> None:
        self.name, self.vendor, self.model, self.cassette = name, vendor, model, cassette

    async def complete(
        self, messages: list[Message], *, schema: dict[str, Any], schema_name: str, timeout_s: float
    ) -> LLMResponse:
        entry = self.cassette.entries.get(request_key(self.name, self.model, schema_name, messages))
        if entry is None:
            raise ProviderError("unavailable", "not in cassette")
        return LLMResponse(
            content=dict(entry["content"]), provider=self.name, vendor=self.vendor, model=self.model,
            input_tokens=entry["input_tokens"], output_tokens=entry["output_tokens"],
            latency_ms=entry["latency_ms"], cost_usd=entry["cost_usd"],
        )  # fmt: skip


def with_cassette(
    providers: dict[str, LLMProvider], mode: str, path: Path
) -> tuple[dict[str, LLMProvider], Cassette | None]:
    if mode == "off":
        return providers, None
    cassette = Cassette(path)
    if mode == "record":
        return {n: RecordingProvider(p, cassette) for n, p in providers.items()}, cassette
    replay: dict[str, LLMProvider] = {
        name: ReplayProvider(name, meta["vendor"], meta["model"], cassette)
        for name, meta in cassette.providers.items()
    }
    return replay, cassette
