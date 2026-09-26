from functools import cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import hash_password, verify_password
from app.models import User


@cache
def _dummy_hash() -> str:
    return hash_password("timing-equalizer")


def _verify_against_dummy(password: str) -> bool:
    return verify_password(_dummy_hash(), password)


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    # Argon2 is deliberately slow and CPU-bound: keep it off the event loop.
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        await run_in_threadpool(_verify_against_dummy, password)  # equalize timing
        return None
    ok = await run_in_threadpool(verify_password, user.password_hash, password)
    return user if ok else None
