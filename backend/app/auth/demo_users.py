import uuid
from typing import Any, cast

from sqlalchemy import CursorResult
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import Role, User

DEMO_USERS: list[tuple[str, str, Role]] = [
    ("viewer@demo.vn", "Nguyễn Minh Anh", Role.viewer),
    ("analyst@demo.vn", "Trần Quốc Bảo", Role.analyst),
    ("admin@demo.vn", "Lê Thu Hà", Role.admin),
]


async def seed_demo_users(session: AsyncSession, password: str) -> int:
    """Insert demo accounts that do not exist yet. Returns number of rows created."""
    password_hash = hash_password(password)
    statement = (
        insert(User)
        .values(
            [
                {
                    "id": uuid.uuid4(),
                    "email": email,
                    "name": name,
                    "role": role,
                    "password_hash": password_hash,
                }
                for email, name, role in DEMO_USERS
            ]
        )  # fmt: skip
        .on_conflict_do_nothing(index_elements=["email"])
    )
    result = cast(CursorResult[Any], await session.execute(statement))
    await session.commit()
    return result.rowcount
