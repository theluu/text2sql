from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import CurrentUser
from app.auth.schemas import LoginRequest, LoginResponse, UserOut
from app.auth.service import authenticate
from app.core.config import Settings
from app.core.db import get_session
from app.core.security import create_access_token

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    user = await authenticate(session, body.email, body.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid_credentials")
    settings: Settings = request.app.state.settings
    token = create_access_token(
        subject=str(user.id),
        role=user.role.value,
        secret=settings.jwt_secret.get_secret_value(),
        ttl_minutes=settings.jwt_ttl_minutes,
    )
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
