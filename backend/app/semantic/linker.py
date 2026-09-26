"""Schema linking: pick the tables, metrics and glossary entries a question needs."""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SchemaEmbedding
from app.semantic.embedder import Embedder, HashingEmbedder
from app.semantic.loader import SemanticLayer

log = structlog.get_logger()

MAX_TABLES = 7
DEFAULT_TABLES = ("orders", "order_items", "products")


@dataclass(frozen=True)
class SchemaDoc:
    object_type: str  # table | column | metric | glossary
    object_ref: str
    text: str


@dataclass
class LinkedSchema:
    tables: list[str]
    metrics: list[str] = field(default_factory=list)
    glossary: list[str] = field(default_factory=list)
    hits: list[tuple[str, float]] = field(default_factory=list)
    method: str = "lexical"

    def to_detail(self) -> dict[str, Any]:
        return {
            "tables": self.tables,
            "metrics": self.metrics,
            "method": self.method,
            "hits": [{"ref": ref, "score": round(score, 3)} for ref, score in self.hits[:8]],
        }


def schema_docs(layer: SemanticLayer) -> list[SchemaDoc]:
    docs: list[SchemaDoc] = []
    for table in layer.tables.values():
        if table.is_view:
            continue
        docs.append(
            SchemaDoc("table", table.name, f"{table.name.replace('_', ' ')} {table.vi} {table.en}")
        )
        for col in table.columns.values():
            sample = " ".join(col.sample)
            text = f"{table.name.replace('_', ' ')} {col.name.replace('_', ' ')} {col.vi} {col.en} {sample}"
            docs.append(SchemaDoc("column", f"{table.name}.{col.name}", text))
    for metric in layer.metrics.values():
        docs.append(
            SchemaDoc(
                "metric", metric.name, f"{metric.name.replace('_', ' ')} {metric.vi} {metric.en}"
            )
        )
    for term in layer.glossary:
        docs.append(SchemaDoc("glossary", term.maps_to, f"{term.term} {term.en}"))
    return docs


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def index_version(layer: SemanticLayer, embedder: Embedder) -> str:
    return f"{layer.version}:{embedder.name}"[:64]


async def sync_schema_embeddings(
    session: AsyncSession, layer: SemanticLayer, embedder: Embedder
) -> bool:
    """Re-embed the semantic layer when the file or the embedder changed. Returns True if rebuilt."""
    version = index_version(layer, embedder)
    existing = await session.scalar(
        select(SchemaEmbedding.id).where(SchemaEmbedding.schema_version == version).limit(1)
    )
    if existing is not None:
        return False
    docs = schema_docs(layer)
    vectors = await embedder.embed([d.text for d in docs])
    await session.execute(delete(SchemaEmbedding))
    session.add_all(
        SchemaEmbedding(
            object_type=d.object_type,
            object_ref=d.object_ref,
            text=d.text,
            embedding=v,
            schema_version=version,
        )
        for d, v in zip(docs, vectors, strict=True)
    )
    await session.commit()
    log.info("schema_embeddings.rebuilt", version=version, docs=len(docs))
    return True


class SchemaLinker:
    def __init__(self, layer: SemanticLayer, embedder: Embedder) -> None:
        self.layer = layer
        self.embedder = embedder
        self._lexical = HashingEmbedder()
        self._docs = schema_docs(layer)
        self._doc_vectors = [self._lexical.embed_one(d.text) for d in self._docs]
        self._graph = self._fk_graph()
        self._pii_tables = {t for t, _ in layer.pii_columns()}

    def _fk_graph(self) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {
            n: set() for n, t in self.layer.tables.items() if not t.is_view
        }
        for table in self.layer.tables.values():
            if table.is_view:
                continue
            for col in table.columns.values():
                if col.fk:
                    target = col.fk.split(".")[0]
                    if target != table.name:
                        graph[table.name].add(target)
                        graph[target].add(table.name)
        return graph

    def lexical_hits(self, question: str, k: int) -> list[tuple[SchemaDoc, float]]:
        query = self._lexical.embed_one(question)
        scored = [
            (d, _cosine(query, v)) for d, v in zip(self._docs, self._doc_vectors, strict=True)
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return [(d, s) for d, s in scored[:k] if s > 0]

    async def _vector_hits(
        self, session: AsyncSession, question: str, k: int
    ) -> list[tuple[SchemaDoc, float]]:
        [query] = await self.embedder.embed([question])
        distance = SchemaEmbedding.embedding.cosine_distance(query)
        rows = await session.execute(
            select(
                SchemaEmbedding.object_type,
                SchemaEmbedding.object_ref,
                SchemaEmbedding.text,
                distance,
            )
            .where(SchemaEmbedding.schema_version == index_version(self.layer, self.embedder))
            .order_by(distance)
            .limit(k)
        )
        return [(SchemaDoc(t, r, txt), 1.0 - float(d)) for t, r, txt, d in rows]

    async def link(self, session: AsyncSession | None, question: str, k: int = 16) -> LinkedSchema:
        hits = self.lexical_hits(question, k)
        method = "lexical"
        if session is not None and not isinstance(self.embedder, HashingEmbedder):
            try:
                vector_hits = await self._vector_hits(session, question, k)
                if vector_hits:
                    # Hybrid: semantic hits first, keyword hits fill in exact-term matches.
                    hits = vector_hits + hits[: k // 2]
                    method = "vector+lexical"
            except Exception as exc:  # embedding API down → keyword fallback
                log.warning("linker.vector_failed", error=str(exc))
                method = "lexical_fallback"
        return self._resolve(hits, method)

    def _resolve(self, hits: list[tuple[SchemaDoc, float]], method: str) -> LinkedSchema:
        top = max((s for _, s in hits), default=0.0)
        tables: list[str] = []
        metrics: list[str] = []
        glossary: list[str] = []

        def add_table(name: str) -> None:
            if name in self._graph and name not in tables:
                tables.append(name)

        for doc, score in hits:
            if score < 0.3 * top:
                continue
            ref = doc.object_ref
            if doc.object_type == "table":
                add_table(ref)
            elif doc.object_type == "column":
                add_table(ref.split(".")[0])
            elif doc.object_type == "metric":
                self._add_metric(ref, metrics, add_table)
            else:
                glossary.append(ref)
                kind, _, target = ref.partition(".")
                if kind == "metric":
                    self._add_metric(target, metrics, add_table)
                else:
                    add_table(target.split(".")[0])
        if not tables:
            tables.extend(DEFAULT_TABLES)
        tables = self._connect(tables[:MAX_TABLES])
        return LinkedSchema(
            tables=tables,
            metrics=metrics,
            glossary=list(dict.fromkeys(glossary)),
            hits=[(d.object_ref, s) for d, s in hits],
            method=method,
        )

    def _add_metric(self, name: str, metrics: list[str], add_table: Any) -> None:
        metric = self.layer.metrics.get(name)
        if metric and name not in metrics:
            metrics.append(name)
            for table in metric.tables:
                add_table(table)

    def _connect(self, tables: list[str]) -> list[str]:
        """Add bridge tables so every linked table is reachable from the first one."""
        result = list(tables)
        for target in tables[1:]:
            path = self._path(result[0], target)
            for node in path:
                if node not in result:
                    result.append(node)
        return result

    def _path(self, start: str, goal: str) -> list[str]:
        previous: dict[str, str | None] = {start: None}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            if node == goal:
                break
            # Bridge through non-PII tables first (regions via stores, not customers).
            for nxt in sorted(self._graph[node], key=lambda t: (t in self._pii_tables, t)):
                if nxt not in previous:
                    previous[nxt] = node
                    queue.append(nxt)
        if goal not in previous:
            return []
        path: list[str] = []
        cursor: str | None = goal
        while cursor is not None:
            path.append(cursor)
            cursor = previous[cursor]
        return path[::-1]


def render_schema(layer: SemanticLayer, linked: LinkedSchema, role: str) -> str:
    """Compact schema block for the prompt, with the relation names this role may query."""
    lines: list[str] = []
    for name in linked.tables:
        relation = layer.visible_name(name, role)
        table = layer.tables[relation]
        lines.append(f"TABLE {relation} -- {table.vi} / {table.en}")
        for col in table.columns.values():
            extra = (
                f" -> {layer.visible_name(col.fk.split('.')[0], role)}.{col.fk.split('.')[1]}"
                if col.fk
                else ""
            )
            sample = f" e.g. {', '.join(col.sample[:4])}" if col.sample else ""
            pii = " [PII]" if col.pii else ""
            lines.append(f"  {col.name} {col.type}{extra} -- {col.vi} / {col.en}{sample}{pii}")
    if linked.metrics:
        lines.append("METRICS")
        for name in linked.metrics:
            metric = layer.metrics[name]
            where = f" WHERE {metric.filter}" if metric.filter else ""
            lines.append(f"  {name} ({metric.vi} / {metric.en}) = {metric.sql}{where}")
    return "\n".join(lines)


def cosine(a: list[float], b: list[float]) -> float:
    return _cosine(a, b) / ((math.sqrt(_cosine(a, a)) * math.sqrt(_cosine(b, b))) or 1.0)
