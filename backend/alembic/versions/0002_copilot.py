"""copilot: pipeline audit, HITL, eval, embeddings

Revision ID: 0002
Revises: 0001
"""

from collections.abc import Sequence

import pgvector.sqlalchemy.vector
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eval_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("suite", sa.String(length=20), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("gold_sql", sa.Text(), nullable=True),
        sa.Column("expected_behavior", sa.String(length=10), nullable=False),
        sa.Column("difficulty", sa.String(length=10), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.String(length=30)), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_eval_cases_suite"), "eval_cases", ["suite"], unique=False)
    op.create_table(
        "schema_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("object_type", sa.String(length=20), nullable=False),
        sa.Column("object_ref", sa.String(length=120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_schema_embeddings_schema_version"),
        "schema_embeddings",
        ["schema_version"],
        unique=False,
    )
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"], unique=False)
    op.create_table(
        "eval_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("suite", sa.String(length=20), nullable=False),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=False),
        sa.Column("model_chain", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("mode", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_runs_created_by"), "eval_runs", ["created_by"], unique=False)
    op.create_table(
        "verified_examples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("sql", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_verified_examples_approved_by"), "verified_examples", ["approved_by"], unique=False
    )
    op.create_table(
        "eval_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("eval_run_id", sa.Uuid(), nullable=False),
        sa.Column("eval_case_id", sa.Uuid(), nullable=False),
        sa.Column("predicted_sql", sa.Text(), nullable=True),
        sa.Column("behavior", sa.String(length=10), nullable=False),
        sa.Column("ex_match", sa.Boolean(), nullable=True),
        sa.Column("esm_match", sa.Boolean(), nullable=True),
        sa.Column("judge_verdict", sa.String(length=20), nullable=True),
        sa.Column("guardrail_code", sa.String(length=40), nullable=True),
        sa.Column("provider_used", sa.String(length=40), nullable=True),
        sa.Column("used_fallback", sa.Boolean(), nullable=False),
        sa.Column("linked_tables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["eval_case_id"], ["eval_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_eval_results_eval_case_id"), "eval_results", ["eval_case_id"], unique=False
    )
    op.create_index(
        op.f("ix_eval_results_eval_run_id"), "eval_results", ["eval_run_id"], unique=False
    )
    op.create_table(
        "query_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("lang", sa.String(length=5), nullable=False),
        sa.Column("rewritten_question", sa.Text(), nullable=True),
        sa.Column("final_sql", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("risk_decision", sa.String(length=20), nullable=True),
        sa.Column("review_reasons", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("provider_used", sa.String(length=40), nullable=True),
        sa.Column("used_fallback", sa.Boolean(), nullable=False),
        sa.Column("guardrail_code", sa.String(length=40), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("result_preview", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("chart_spec", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_query_runs_conversation_id"), "query_runs", ["conversation_id"], unique=False
    )
    op.create_index(op.f("ix_query_runs_status"), "query_runs", ["status"], unique=False)
    op.create_index(op.f("ix_query_runs_user_id"), "query_runs", ["user_id"], unique=False)
    op.create_table(
        "guardrail_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid(), nullable=True),
        sa.Column("layer", sa.String(length=4), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_guardrail_events_code"), "guardrail_events", ["code"], unique=False)
    op.create_index(
        op.f("ix_guardrail_events_query_run_id"), "guardrail_events", ["query_run_id"], unique=False
    )
    op.create_table(
        "judge_verdicts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid(), nullable=False),
        sa.Column("judge_model", sa.String(length=80), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("rubric", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("issues", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("same_vendor", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_judge_verdicts_query_run_id"), "judge_verdicts", ["query_run_id"], unique=False
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid(), nullable=True),
        sa.Column("eval_result_id", sa.Uuid(), nullable=True),
        sa.Column("purpose", sa.String(length=20), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["eval_result_id"], ["eval_results.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_calls_eval_result_id"), "llm_calls", ["eval_result_id"], unique=False
    )
    op.create_index(op.f("ix_llm_calls_provider"), "llm_calls", ["provider"], unique=False)
    op.create_index(op.f("ix_llm_calls_query_run_id"), "llm_calls", ["query_run_id"], unique=False)
    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid(), nullable=False),
        sa.Column("step", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pipeline_steps_query_run_id"), "pipeline_steps", ["query_run_id"], unique=False
    )
    op.create_table(
        "review_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid(), nullable=False),
        sa.Column("reasons", postgresql.ARRAY(sa.String(length=40)), nullable=False),
        sa.Column("risk_weight", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("assignee_id", sa.Uuid(), nullable=True),
        sa.Column("original_sql", sa.Text(), nullable=True),
        sa.Column("final_sql", sa.Text(), nullable=True),
        sa.Column("reviewer_note", sa.Text(), nullable=True),
        sa.Column("add_to_golden", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_items_assignee_id"), "review_items", ["assignee_id"], unique=False
    )
    op.create_index(
        op.f("ix_review_items_query_run_id"), "review_items", ["query_run_id"], unique=False
    )
    op.create_index(op.f("ix_review_items_status"), "review_items", ["status"], unique=False)
    op.create_table(
        "user_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("query_run_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("rating", sa.String(length=4), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["query_run_id"], ["query_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_feedback_query_run_id"), "user_feedback", ["query_run_id"], unique=False
    )
    op.create_index(op.f("ix_user_feedback_user_id"), "user_feedback", ["user_id"], unique=False)
    op.create_table(
        "judge_disagreements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_item_id", sa.Uuid(), nullable=False),
        sa.Column("judge_verdict", sa.String(length=20), nullable=False),
        sa.Column("human_verdict", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["review_item_id"], ["review_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_judge_disagreements_review_item_id"),
        "judge_disagreements",
        ["review_item_id"],
        unique=False,
    )
    for table in ("schema_embeddings", "verified_examples"):
        op.execute(
            f"CREATE INDEX ix_{table}_embedding_hnsw ON {table}"
            " USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_judge_disagreements_review_item_id"), table_name="judge_disagreements")
    op.drop_table("judge_disagreements")
    op.drop_index(op.f("ix_user_feedback_user_id"), table_name="user_feedback")
    op.drop_index(op.f("ix_user_feedback_query_run_id"), table_name="user_feedback")
    op.drop_table("user_feedback")
    op.drop_index(op.f("ix_review_items_status"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_query_run_id"), table_name="review_items")
    op.drop_index(op.f("ix_review_items_assignee_id"), table_name="review_items")
    op.drop_table("review_items")
    op.drop_index(op.f("ix_pipeline_steps_query_run_id"), table_name="pipeline_steps")
    op.drop_table("pipeline_steps")
    op.drop_index(op.f("ix_llm_calls_query_run_id"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_provider"), table_name="llm_calls")
    op.drop_index(op.f("ix_llm_calls_eval_result_id"), table_name="llm_calls")
    op.drop_table("llm_calls")
    op.drop_index(op.f("ix_judge_verdicts_query_run_id"), table_name="judge_verdicts")
    op.drop_table("judge_verdicts")
    op.drop_index(op.f("ix_guardrail_events_query_run_id"), table_name="guardrail_events")
    op.drop_index(op.f("ix_guardrail_events_code"), table_name="guardrail_events")
    op.drop_table("guardrail_events")
    op.drop_index(op.f("ix_query_runs_user_id"), table_name="query_runs")
    op.drop_index(op.f("ix_query_runs_status"), table_name="query_runs")
    op.drop_index(op.f("ix_query_runs_conversation_id"), table_name="query_runs")
    op.drop_table("query_runs")
    op.drop_index(op.f("ix_eval_results_eval_run_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_eval_case_id"), table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_index(op.f("ix_verified_examples_approved_by"), table_name="verified_examples")
    op.drop_table("verified_examples")
    op.drop_index(op.f("ix_eval_runs_created_by"), table_name="eval_runs")
    op.drop_table("eval_runs")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_schema_embeddings_schema_version"), table_name="schema_embeddings")
    op.drop_table("schema_embeddings")
    op.drop_index(op.f("ix_eval_cases_suite"), table_name="eval_cases")
    op.drop_table("eval_cases")
