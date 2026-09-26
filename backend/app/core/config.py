from datetime import date
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

    redis_url: str = "redis://redis:6379/0"
    # Relative dates ("tháng trước", "this quarter") resolve against this day, the last
    # day of seeded data, so answers and eval results are reproducible.
    data_as_of: date = date(2026, 8, 31)

    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5-mini"
    # Reasoning models (gpt-5*, o*): effort for SQL generation; judge/classify/rewrite use "minimal".
    openai_reasoning_effort: str = "low"
    openai_embedding_model: str = "text-embedding-3-small"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    ollama_base_url: str | None = None
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_embedding_model: str = "bge-m3"

    # Router timing. The spec's 20 s budget is too tight for reasoning models such as
    # gpt-5-mini (≈12-20 s per SQL generation), so both are configurable.
    llm_call_timeout_s: float = 30.0
    llm_budget_s: float = 45.0

    @field_validator("anthropic_api_key", "openai_api_key", "gemini_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("ollama_base_url", mode="before")
    @classmethod
    def _blank_url_is_none(cls, value: object) -> object:
        return None if value == "" else value

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
