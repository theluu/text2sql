import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import Depends

from app.auth.deps import require_min_role
from app.core.config import Settings
from app.core.security import create_access_token
from app.main import create_app
from app.models import Role
from tests.helpers import DEMO_PASSWORD, login_token


async def test_login_returns_token_and_profile(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": "analyst@demo.vn", "password": DEMO_PASSWORD}
    )
    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "analyst"
    assert body["user"]["name"] == "Trần Quốc Bảo"


async def test_login_email_is_case_insensitive(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/login", json={"email": "Viewer@Demo.VN", "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("email", "password"),
    [("viewer@demo.vn", "wrong-password"), ("nobody@demo.vn", DEMO_PASSWORD)],
)
async def test_bad_credentials_do_not_reveal_which_part_failed(
    client: httpx.AsyncClient, email: str, password: str
) -> None:
    response = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid_credentials"}


async def test_me_returns_current_user(client: httpx.AsyncClient) -> None:
    token = await login_token(client, "admin@demo.vn")
    response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "admin@demo.vn"


async def test_me_without_token_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "not_authenticated"}


async def test_tampered_expired_and_orphan_tokens_are_401(
    client: httpx.AsyncClient, pg_settings: Settings
) -> None:
    secret = pg_settings.jwt_secret.get_secret_value()
    good = await login_token(client, "viewer@demo.vn")
    head, body, _ = good.split(".")
    tampered = f"{head}.{body}.{'A' * 43}"
    expired = create_access_token(
        subject=str(uuid.uuid4()), role="viewer", secret=secret, ttl_minutes=5,
        now=datetime.now(UTC) - timedelta(days=1),
    )  # fmt: skip
    orphan = create_access_token(
        subject=str(uuid.uuid4()), role="admin", secret=secret, ttl_minutes=5
    )
    not_a_uuid = create_access_token(subject="42", role="admin", secret=secret, ttl_minutes=5)
    for token in (tampered, expired, orphan, not_a_uuid, "garbage"):
        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, token
        assert response.json() == {"detail": "not_authenticated"}


@pytest.mark.parametrize(
    ("email", "expected"),
    [("viewer@demo.vn", 403), ("analyst@demo.vn", 200), ("admin@demo.vn", 200)],
)
async def test_require_min_role_enforces_hierarchy(
    pg_settings: Settings, demo_users: None, email: str, expected: int
) -> None:
    app = create_app(pg_settings)

    @app.get("/api/_probe", dependencies=[Depends(require_min_role(Role.analyst))])
    async def probe() -> dict[str, bool]:
        return {"ok": True}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        token = await login_token(http, email)
        response = await http.get("/api/_probe", headers={"Authorization": f"Bearer {token}"})
    await app.state.engine.dispose()
    assert response.status_code == expected
    if expected == 403:
        assert response.json() == {"detail": "forbidden"}
