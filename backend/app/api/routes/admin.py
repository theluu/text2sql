from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import require_min_role
from app.core.db import get_session
from app.llm.registry import DEFAULT_CHAIN, KNOWN_PROVIDERS
from app.models import Role, User
from app.pipeline.risk import RiskSettings
from app.services.app_settings import load_app_settings, save_app_setting
from app.services.deps import ServicesDep

router = APIRouter(tags=["admin"])
Session = Annotated[AsyncSession, Depends(get_session)]
Admin = Annotated[User, Depends(require_min_role(Role.admin))]


class RiskBody(BaseModel):
    review_confidence: float = Field(ge=0, le=1)
    fallback_confidence: float = Field(ge=0, le=1)
    gray_cost: float = Field(gt=0)
    max_cost: float = Field(gt=0)
    w_self: float = Field(ge=0, le=1)
    w_judge: float = Field(ge=0, le=1)
    w_agreement: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _coherent(self) -> "RiskBody":
        if self.gray_cost >= self.max_cost:
            raise ValueError("gray_cost must be below max_cost")
        if self.w_self + self.w_judge + self.w_agreement <= 0:
            raise ValueError("confidence weights cannot all be zero")
        return self


class ChaosBody(BaseModel):
    disabled_providers: list[str] = Field(default_factory=list)

    @field_validator("disabled_providers")
    @classmethod
    def _known(cls, value: list[str]) -> list[str]:
        unknown = set(value) - set(KNOWN_PROVIDERS)
        if unknown:
            raise ValueError(f"unknown providers: {sorted(unknown)}")
        return sorted(set(value))


class FeaturesBody(BaseModel):
    llm_classifier: bool = True
    self_consistency: bool = True
    cache: bool = True


class SettingsBody(BaseModel):
    llm_chain: list[str] | None = None
    chaos: ChaosBody | None = None
    risk: RiskBody | None = None
    features: FeaturesBody | None = None

    @field_validator("llm_chain")
    @classmethod
    def _chain(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if sorted(value) != sorted(DEFAULT_CHAIN):
            raise ValueError(f"chain must be a permutation of {DEFAULT_CHAIN}")
        if value[-1] != "rule_based":
            raise ValueError("rule_based must stay last: it is the no-LLM safety net")
        return value


async def settings_view(session: AsyncSession, services: Any) -> dict[str, Any]:
    values = await load_app_settings(session)
    return {
        **{k: values[k] for k in ("llm_chain", "chaos", "risk", "features")},
        "risk_defaults": {k: getattr(RiskSettings(), k) for k in RiskSettings.__dataclass_fields__},
        "providers": [
            {
                "name": name,
                "configured": name in services.providers,
                "model": services.providers[name].model if name in services.providers else None,
                "circuit": await services.breaker.state(name)
                if name in services.providers
                else None,
            }
            for name in KNOWN_PROVIDERS
        ],  # fmt: skip
    }


@router.get("/admin/settings")
async def get_settings(_: Admin, session: Session, services: ServicesDep) -> dict[str, Any]:
    return await settings_view(session, services)


@router.put("/admin/settings")
async def put_settings(
    body: SettingsBody, admin: Admin, session: Session, services: ServicesDep
) -> dict[str, Any]:
    for key, value in body.model_dump(exclude_none=True).items():
        await save_app_setting(session, key, value, admin.id)
    return await settings_view(session, services)


@router.post("/admin/circuits/{provider}/reset")
async def reset_circuit(provider: str, _: Admin, services: ServicesDep) -> dict[str, str]:
    if provider not in KNOWN_PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown_provider")
    await services.breaker.record_success(provider)
    return {"state": await services.breaker.state(provider)}


@router.get("/admin/semantic")
async def semantic(_: Admin, services: ServicesDep) -> dict[str, Any]:
    layer = services.layer
    return {
        "version": layer.version,
        "embedder": services.embedder.name,
        "tables": [
            {
                "name": t.name, "vi": t.vi, "en": t.en, "view_of": t.base, "viewer_via": t.viewer_via,
                "columns": [{"name": c.name, "type": c.type, "vi": c.vi, "en": c.en, "pii": c.pii, "fk": c.fk}
                            for c in t.columns.values()],
            }
            for t in layer.tables.values()
        ],
        "metrics": [{"name": m.name, "vi": m.vi, "en": m.en, "sql": m.sql, "filter": m.filter,
                     "tables": list(m.tables)} for m in layer.metrics.values()],
        "glossary": [{"term": g.term, "en": g.en, "maps_to": g.maps_to} for g in layer.glossary],
    }  # fmt: skip
