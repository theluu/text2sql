import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db import get_session
from app.core.security import decode_access_token
from app.models import Role, User

ROLE_RANK: dict[Role, int] = {Role.viewer: 0, Role.analyst: 1, Role.admin: 2}
_bearer = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        detail="not_authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if credentials is None:
        raise _unauthorized()
    settings: Settings = request.app.state.settings
    try:
        claims = decode_access_token(
            credentials.credentials, secret=settings.jwt_secret.get_secret_value()
        )
        user_id = uuid.UUID(claims.sub)
    except (jwt.InvalidTokenError, ValueError):
        raise _unauthorized() from None
    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_min_role(minimum: Role) -> Callable[[User], Awaitable[User]]:
    async def dependency(user: CurrentUser) -> User:
        if ROLE_RANK[user.role] < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="forbidden")
        return user

    return dependency
