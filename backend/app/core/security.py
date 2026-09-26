from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import BaseModel

ALGORITHM = "HS256"
_hasher = PasswordHasher()


class TokenClaims(BaseModel):
    sub: str
    role: str
    exp: int


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(
    *, subject: str, role: str, secret: str, ttl_minutes: int, now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> TokenClaims:
    payload = jwt.decode(
        token, secret, algorithms=[ALGORITHM], options={"require": ["sub", "role", "exp"]}
    )
    return TokenClaims.model_validate(payload)
