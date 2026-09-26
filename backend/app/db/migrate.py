from pathlib import Path

from alembic.config import Config

from alembic import command

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _config(app_db_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", app_db_url.replace("%", "%%"))
    return config


def upgrade_head(app_db_url: str) -> None:
    command.upgrade(_config(app_db_url), "head")


def downgrade_base(app_db_url: str) -> None:
    command.downgrade(_config(app_db_url), "base")
