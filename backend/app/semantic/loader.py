import hashlib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import yaml

SEMANTIC_FILE = Path(__file__).parent / "warehouse.yaml"
# Tables whose raw form is off-limits to viewers; they read the masked view instead.
PRIVILEGED_ROLES = frozenset({"analyst", "admin"})


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    vi: str
    en: str
    pii: bool = False
    fk: str | None = None
    sample: tuple[str, ...] = ()


@dataclass(frozen=True)
class Table:
    name: str
    vi: str
    en: str
    columns: dict[str, Column]
    viewer_via: str | None = None
    base: str | None = None  # set for views

    @property
    def is_view(self) -> bool:
        return self.base is not None


@dataclass(frozen=True)
class Metric:
    name: str
    vi: str
    en: str
    sql: str
    tables: tuple[str, ...]
    filter: str | None = None


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    en: str
    maps_to: str


@dataclass(frozen=True)
class SemanticLayer:
    tables: dict[str, Table]
    metrics: dict[str, Metric]
    glossary: tuple[GlossaryTerm, ...]
    version: str
    raw: dict[str, Any] = field(repr=False, compare=False)

    def allowed_tables(self, role: str) -> set[str]:
        if role in PRIVILEGED_ROLES:
            return set(self.tables)
        return {name for name, table in self.tables.items() if table.viewer_via is None}

    def visible_name(self, table: str, role: str) -> str:
        """The relation a role should query for `table` (masked view for viewers)."""
        via = self.tables[table].viewer_via
        return via if via and role not in PRIVILEGED_ROLES else table

    def pii_columns(self) -> set[tuple[str, str]]:
        return {
            (table.name, column.name)
            for table in self.tables.values()
            for column in table.columns.values()
            if column.pii
        }


def _column(name: str, spec: dict[str, Any]) -> Column:
    return Column(
        name=name,
        type=spec["type"],
        vi=spec["vi"],
        en=spec["en"],
        pii=bool(spec.get("pii", False)),
        fk=spec.get("fk"),
        sample=tuple(str(s) for s in spec.get("sample", [])),
    )


def parse(text: str) -> SemanticLayer:
    raw: dict[str, Any] = yaml.safe_load(text)
    tables: dict[str, Table] = {}
    for name, spec in raw["tables"].items():
        columns = {col: _column(col, cspec) for col, cspec in spec["columns"].items()}
        tables[name] = Table(name, spec["vi"], spec["en"], columns, spec.get("viewer_via"))
    for name, spec in raw.get("views", {}).items():
        base = tables[spec["base"]]
        columns = {col: base.columns[col] for col in spec["columns"]}
        tables[name] = Table(name, spec["vi"], spec["en"], columns, base=base.name)
    metrics = {
        name: Metric(name, m["vi"], m["en"], m["sql"], tuple(m["tables"]), m.get("filter"))
        for name, m in raw.get("metrics", {}).items()
    }
    glossary = tuple(
        GlossaryTerm(g["term"], g["en"], g["maps_to"]) for g in raw.get("glossary", [])
    )
    version = hashlib.sha256(text.encode()).hexdigest()[:16]
    return SemanticLayer(tables, metrics, glossary, version, raw)


@cache
def load_semantic_layer() -> SemanticLayer:
    return parse(SEMANTIC_FILE.read_text(encoding="utf-8"))
