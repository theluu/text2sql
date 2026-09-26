from typing import Any

import httpx

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


DEMO_PASSWORD = "demo1234"


async def login_token(client: httpx.AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])
