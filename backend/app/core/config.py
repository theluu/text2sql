from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WarehouseRole = Literal["admin", "viewer", "analyst"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["dev", "test", "prod"] = "dev"
    app_db_url: str

    warehouse_host: str
    warehouse_port: int = 5432
    warehouse_db: str = "warehouse"
    warehouse_admin_user: str
    warehouse_admin_password: SecretStr
    warehouse_viewer_password: SecretStr
    warehouse_analyst_password: SecretStr
    warehouse_seed_scale: float = 1.0

    jwt_secret: SecretStr
    jwt_ttl_minutes: int = 480
    demo_password: SecretStr = SecretStr("demo1234")

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_is_strong(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return value

    def warehouse_dsn(self, role: WarehouseRole = "admin") -> str:
        credentials = {
            "admin": (self.warehouse_admin_user, self.warehouse_admin_password),
            "viewer": ("wh_viewer", self.warehouse_viewer_password),
            "analyst": ("wh_analyst", self.warehouse_analyst_password),
        }
        user, password = credentials[role]
        secret = quote(password.get_secret_value(), safe="")
        return (
            f"postgresql://{quote(user, safe='')}:{secret}"
            f"@{self.warehouse_host}:{self.warehouse_port}/{self.warehouse_db}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
