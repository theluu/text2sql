import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models._types import EMBEDDING_DIM, created_at, fk, pk
from app.models.base import Base


def _hnsw(table: str) -> Index:
    return Index(
        f"ix_{table}_embedding_hnsw",
        "embedding",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[uuid.UUID] = pk()
    query_run_id: Mapped[uuid.UUID] = fk("query_runs.id")
    user_id: Mapped[uuid.UUID] = fk("users.id")
    rating: Mapped[str] = mapped_column(String(4))
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = pk()
    query_run_id: Mapped[uuid.UUID] = fk("query_runs.id")
    reasons: Mapped[list[str]] = mapped_column(ARRAY(String(40)))
    risk_weight: Mapped[float] = mapped_column(Float, default=1.0)
    # open | claimed | approved | edited | rejected | returned
    status: Mapped[str] = mapped_column(String(20), index=True, default="open")
    assignee_id: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    original_sql: Mapped[str | None] = mapped_column(Text)
    final_sql: Mapped[str | None] = mapped_column(Text)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    add_to_golden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = created_at()
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JudgeDisagreement(Base):
    __tablename__ = "judge_disagreements"

    id: Mapped[uuid.UUID] = pk()
    review_item_id: Mapped[uuid.UUID] = fk("review_items.id")
    judge_verdict: Mapped[str] = mapped_column(String(20))
    human_verdict: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = created_at()


class VerifiedExample(Base):
    __tablename__ = "verified_examples"
    __table_args__ = (_hnsw("verified_examples"),)

    id: Mapped[uuid.UUID] = pk()
    question: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(5))
    sql: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    approved_by: Mapped[uuid.UUID | None] = fk("users.id", nullable=True, ondelete="SET NULL")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = created_at()


class SchemaEmbedding(Base):
    __tablename__ = "schema_embeddings"
    __table_args__ = (_hnsw("schema_embeddings"),)

    id: Mapped[uuid.UUID] = pk()
    object_type: Mapped[str] = mapped_column(String(20))
    object_ref: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    schema_version: Mapped[str] = mapped_column(String(64), index=True)
