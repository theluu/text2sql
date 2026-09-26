"""Keep stored vectors in the current embedder's space (run at startup)."""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting, VerifiedExample
from app.semantic.embedder import Embedder
from app.semantic.linker import sync_schema_embeddings
from app.semantic.loader import SemanticLayer
from app.services.app_settings import save_app_setting

log = structlog.get_logger()


async def sync_embeddings(session: AsyncSession, layer: SemanticLayer, embedder: Embedder) -> None:
    rebuilt = await sync_schema_embeddings(session, layer, embedder)
    marker = await session.get(AppSetting, "embedding_state")
    if rebuilt or marker is None or marker.value.get("embedder") != embedder.name:
        examples = list(await session.scalars(select(VerifiedExample)))
        if examples:
            vectors = await embedder.embed([e.question for e in examples])
            for example, vector in zip(examples, vectors, strict=True):
                example.embedding = vector
            await session.commit()
            log.info("verified_examples.reembedded", count=len(examples))
        await save_app_setting(session, "embedding_state", {"embedder": embedder.name}, None)
