import threading

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.auth import service
from app.core.config import Settings
from tests.helpers import DEMO_PASSWORD


@pytest.mark.parametrize("email", ["viewer@demo.vn", "nobody@demo.vn"])
async def test_password_check_runs_off_the_event_loop(
    pg_settings: Settings, demo_users: None, monkeypatch: pytest.MonkeyPatch, email: str
) -> None:
    """Argon2 is CPU-bound; running it on the loop thread stalls every other request."""
    loop_thread = threading.get_ident()
    seen: list[int] = []
    real_verify = service.verify_password

    def spy(password_hash: str, password: str) -> bool:
        seen.append(threading.get_ident())
        return real_verify(password_hash, password)

    monkeypatch.setattr(service, "verify_password", spy)
    engine = create_async_engine(pg_settings.app_db_url)
    async with async_sessionmaker(engine)() as session:
        await service.authenticate(session, email, DEMO_PASSWORD)
    await engine.dispose()

    assert seen, "verify_password was not called"
    assert all(ident != loop_thread for ident in seen)
