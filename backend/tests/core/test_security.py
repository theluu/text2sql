from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

SECRET = "s" * 40


def test_password_hash_round_trip() -> None:
    hashed = hash_password("demo1234")
    assert hashed != "demo1234"
    assert verify_password(hashed, "demo1234")
    assert not verify_password(hashed, "wrong")


def test_verify_password_rejects_garbage_hash() -> None:
    assert not verify_password("not-a-hash", "demo1234")


def test_token_round_trip() -> None:
    token = create_access_token(subject="abc", role="analyst", secret=SECRET, ttl_minutes=5)
    claims = decode_access_token(token, secret=SECRET)
    assert (claims.sub, claims.role) == ("abc", "analyst")


def test_expired_token_is_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token = create_access_token(
        subject="abc", role="viewer", secret=SECRET, ttl_minutes=5, now=past
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, secret=SECRET)


def test_token_signed_with_other_secret_is_rejected() -> None:
    token = create_access_token(subject="abc", role="viewer", secret="o" * 40, ttl_minutes=5)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, secret=SECRET)
