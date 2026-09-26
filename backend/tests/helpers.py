from typing import Any

from app.core.config import Settings


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "env": "test",
        "app_db_url": "postgresql+asyncpg://u:p@localhost:5432/app",
        "warehouse_host": "localhost",
        "warehouse_admin_user": "wh_admin",
        "warehouse_admin_password": "admin-pw",
        "warehouse_viewer_password": "viewer-pw",
        "warehouse_analyst_password": "analyst-pw",
        "jwt_secret": "x" * 40,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def sync_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")
