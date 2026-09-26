import pytest
from pydantic import ValidationError

from tests.helpers import make_settings


def test_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="at least 32"):
        make_settings(jwt_secret="too-short")


def test_warehouse_dsn_uses_role_credentials_and_escapes_password() -> None:
    settings = make_settings(warehouse_viewer_password="p@ss/word", warehouse_port=6543)
    dsn = settings.warehouse_dsn("viewer")
    assert dsn == "postgresql://wh_viewer:p%40ss%2Fword@localhost:6543/warehouse"


def test_warehouse_dsn_defaults_to_admin() -> None:
    assert make_settings().warehouse_dsn().startswith("postgresql://wh_admin:admin-pw@")


def test_env_example_jwt_secret_is_not_usable_as_is() -> None:
    """Copying .env.example verbatim must not yield a publicly known signing key."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[3] / ".env.example"
    values = dict(line.split("=", 1) for line in example.read_text().splitlines() if "=" in line)
    with pytest.raises(ValidationError):
        make_settings(jwt_secret=values["JWT_SECRET"])
