from typing import Any

from fastapi import APIRouter

from app.llm.registry import KNOWN_PROVIDERS
from app.services.deps import ServicesDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(services: ServicesDep) -> dict[str, Any]:
    """Liveness plus which LLM providers are configured and their circuit state (no secrets)."""
    providers = [
        {"name": name, "configured": name in services.providers,
         "circuit": await services.breaker.state(name) if name in services.providers else None}
        for name in KNOWN_PROVIDERS
    ]  # fmt: skip
    return {"status": "ok", "providers": providers, "redis": services.redis is not None}
