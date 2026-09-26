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
