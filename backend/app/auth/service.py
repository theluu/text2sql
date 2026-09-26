from functools import cache

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User


@cache
def _dummy_hash() -> str:
    return hash_password("timing-equalizer")


async def authenticate(session: AsyncSession, email: str, password: str) -> User | None:
    user = await session.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        verify_password(_dummy_hash(), password)  # keep timing similar to a real check
        return None
    return user if verify_password(user.password_hash, password) else None
