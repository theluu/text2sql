import psycopg

from app.core.config import Settings
from app.db.migrate import downgrade_base, upgrade_head
from tests.helpers import sync_dsn

COPILOT_TABLES = {
    "conversations", "query_runs", "pipeline_steps", "llm_calls", "judge_verdicts",
    "guardrail_events", "user_feedback", "review_items", "judge_disagreements",
    "verified_examples", "schema_embeddings", "eval_cases", "eval_runs", "eval_results",
}  # fmt: skip


def _tables(dsn: str) -> set[str]:
    with psycopg.connect(dsn) as conn:
        return {
            r[0]
            for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        }


def test_upgrade_creates_tables_and_vector_extension(pg_settings: Settings) -> None:
    url = pg_settings.app_db_url.replace("/app_test", "/app_migration_test")
    upgrade_head(url)
    assert {"users", "app_settings", "alembic_version"} | COPILOT_TABLES <= _tables(sync_dsn(url))
    with psycopg.connect(sync_dsn(url)) as conn:
        assert conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'").fetchone()


def test_migrations_round_trip(pg_settings: Settings) -> None:
    url = pg_settings.app_db_url.replace("/app_test", "/app_migration_test")
    upgrade_head(url)
    downgrade_base(url)
    assert _tables(sync_dsn(url)) <= {"alembic_version"}
    upgrade_head(url)
    assert {"users", "app_settings"} <= _tables(sync_dsn(url))
