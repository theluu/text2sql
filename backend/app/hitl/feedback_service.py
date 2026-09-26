import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import QueryRun, ReviewItem, UserFeedback
from app.pipeline.risk import REASON_WEIGHTS


class FeedbackError(Exception):
    pass


async def record_feedback(
    session: AsyncSession, run_id: uuid.UUID, user_id: uuid.UUID, rating: str, comment: str | None
) -> bool:
    """Store 👍/👎. A 👎 on an auto-executed answer opens a retroactive review. Returns True if it did."""
    run = await session.get(QueryRun, run_id)
    if run is None or run.user_id != user_id:
        raise FeedbackError("not_found")
    session.add(UserFeedback(query_run_id=run.id, user_id=user_id, rating=rating, comment=comment))
    opened = False
    if rating == "down" and run.status == "answered":
        already = await session.scalar(
            select(ReviewItem.id).where(
                ReviewItem.query_run_id == run.id, ReviewItem.status.in_(("open", "claimed"))
            )
        )
        if already is None:
            session.add(ReviewItem(query_run_id=run.id, reasons=["USER_DOWNVOTE"],
                                   risk_weight=REASON_WEIGHTS["USER_DOWNVOTE"], original_sql=run.final_sql))  # fmt: skip
            opened = True
    await session.commit()
    return opened
