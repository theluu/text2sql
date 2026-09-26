"""Runtime-tunable settings stored in `app_settings` (edited on the Admin page)."""

import copy
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.registry import DEFAULT_CHAIN
from app.models import AppSetting
from app.pipeline.risk import RiskSettings

DEFAULTS: dict[str, Any] = {
    "llm_chain": DEFAULT_CHAIN,
    "chaos": {"disabled_providers": []},
    "risk": {k: getattr(RiskSettings(), k) for k in RiskSettings.__dataclass_fields__},
    "features": {"llm_classifier": True, "self_consistency": True, "cache": True},
}


async def load_app_settings(session: AsyncSession) -> dict[str, Any]:
    values = copy.deepcopy(DEFAULTS)
    for row in await session.scalars(select(AppSetting)):
        if row.key in values and isinstance(values[row.key], dict) and isinstance(row.value, dict):
            values[row.key] = {**values[row.key], **row.value}
        elif row.key == "llm_chain" and isinstance(row.value, dict):
            values["llm_chain"] = list(row.value.get("order", DEFAULT_CHAIN))
        else:
            values[row.key] = row.value
    return values


async def save_app_setting(
    session: AsyncSession, key: str, value: Any, user_id: uuid.UUID | None
) -> None:
    stored = {"order": value} if key == "llm_chain" else value
    statement = (
        insert(AppSetting)
        .values(key=key, value=stored, updated_by=user_id)
        .on_conflict_do_update(
            index_elements=["key"], set_={"value": stored, "updated_by": user_id}
        )
    )
    await session.execute(statement)
    await session.commit()
