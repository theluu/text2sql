"""Text embedders, all producing 1024-d unit vectors.

`HashingEmbedder` is local, dependency-free feature hashing over accent-free tokens. It
keeps linking and few-shot retrieval working with no API key (and is the keyword
fallback when an API embedder is down).
"""

import hashlib
import math
from collections.abc import Sequence
from typing import Protocol

import httpx
import structlog

from app.core.text import tokens
from app.models._types import EMBEDDING_DIM

log = structlog.get_logger()

# Words that carry no retrieval signal in either language. ("cua" is absent on purpose:
# unaccented it is both "của" and "cửa" as in cửa hàng.)
STOPWORDS = frozenset(
    [
        "cac",
        "nhung",
        "la",
        "va",
        "o",
        "trong",
        "theo",
        "cho",
        "voi",
        "nao",
        "gi",
        "bao",
        "nhieu",
        "the",
        "thi",
        "co",
        "khong",
        "duoc",
        "mot",
        "the",
        "a",
        "an",
        "of",
        "in",
        "on",
        "for",
        "by",
        "to",
        "and",
        "or",
        "is",
        "are",
        "what",
        "which",
        "how",
        "many",
        "much",
        "show",
        "list",
        "me",
        "give",
    ]
)


class Embedder(Protocol):
    name: str

    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class HashingEmbedder:
    name = "hash-v1"

    def embed_one(self, text: str) -> list[float]:
        words = [w for w in tokens(text) if w not in STOPWORDS]
        features = [(w, 1.0) for w in words]
        features += [(f"{a}_{b}", 1.5) for a, b in zip(words, words[1:], strict=False)]
        vector = [0.0] * EMBEDDING_DIM
        for feature, weight in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % EMBEDDING_DIM
            vector[index] += weight if digest[4] & 1 else -weight
        return _unit(vector)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.name = f"openai:{model}"
        self._key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=15)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self._client.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "input": list(texts), "dimensions": EMBEDDING_DIM},
        )
        response.raise_for_status()
        data = sorted(response.json()["data"], key=lambda d: d["index"])
        return [_unit([float(x) for x in d["embedding"]]) for d in data]


class OllamaEmbedder:
    """bge-m3 via Ollama: 1024-d natively."""

    def __init__(self, base_url: str, model: str, client: httpx.AsyncClient | None = None) -> None:
        self.name = f"ollama:{model}"
        self._url = base_url.rstrip("/")
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=30)

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        response = await self._client.post(
            f"{self._url}/api/embed", json={"model": self._model, "input": list(texts)}
        )
        response.raise_for_status()
        vectors = [[float(x) for x in v] for v in response.json()["embeddings"]]
        if any(len(v) != EMBEDDING_DIM for v in vectors):
            raise ValueError(f"{self.name} returned non-{EMBEDDING_DIM}-d vectors")
        return [_unit(v) for v in vectors]


def build_embedder(
    openai_key: str | None, openai_model: str, ollama_url: str | None, ollama_model: str
) -> Embedder:
    """Pick one embedder for both indexing and querying (vectors must share a space)."""
    if openai_key:
        return OpenAIEmbedder(openai_key, openai_model)
    if ollama_url:
        return OllamaEmbedder(ollama_url, ollama_model)
    return HashingEmbedder()
