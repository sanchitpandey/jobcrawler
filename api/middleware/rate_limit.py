"""
Rate limiting for the free tier.

Free tier  : 5 applications per calendar week (Mon 00:00 UTC → Sun 23:59 UTC).
Paid tier  : unlimited.

Usage
-----
Inject ``check_apply_limit`` as a dependency on any route that consumes an
application slot (currently ``POST /jobs``):

    @router.post("", dependencies=[Depends(check_apply_limit)])
    async def track_job(...): ...

Call ``get_usage`` to read the current counter without consuming a slot
(used by ``GET /jobs/usage``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.models.application import Application
from api.models.base import get_db
from api.models.user import User
from api.routes.auth import get_current_user


def week_start() -> datetime:
    """Monday 00:00:00 UTC of the current ISO week."""
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def next_week_start() -> datetime:
    """Monday 00:00:00 UTC of the *next* ISO week."""
    return week_start() + timedelta(weeks=1)


def retry_after_seconds() -> int:
    """Seconds until the rate-limit window resets (next Monday 00:00 UTC)."""
    delta = next_week_start() - datetime.now(timezone.utc)
    return max(1, int(delta.total_seconds()))


async def _count_this_week(user_id: str, db: AsyncSession) -> int:
    """Return how many applications the user has tracked in the current week."""
    result = await db.execute(
        select(func.count())
        .select_from(Application)
        .where(
            Application.user_id == user_id,
            Application.scored_at >= week_start(),
        )
    )
    return result.scalar_one()


async def check_apply_limit(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Dependency — raises 429 when a free-tier user exceeds their weekly quota.

    Inject this into any route that consumes an application slot.
    Paid-tier users pass through immediately without a DB query.
    """
    if current_user.tier == "paid":
        return

    settings = get_settings()
    used = await _count_this_week(current_user.id, db)

    if used >= settings.free_tier_weekly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Free tier limit reached: {settings.free_tier_weekly_limit} applications "
                f"per week. Upgrade to paid for unlimited applications."
            ),
            headers={"Retry-After": str(retry_after_seconds())},
        )


class UsageInfo:
    """Snapshot of the current user's rate-limit usage."""

    __slots__ = ("used", "limit", "resets_at", "is_paid")

    def __init__(self, used: int, limit: int, resets_at: datetime, is_paid: bool) -> None:
        self.used = used
        self.limit = limit
        self.resets_at = resets_at
        self.is_paid = is_paid


async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageInfo:
    """Dependency — returns usage info without consuming a slot."""
    settings = get_settings()
    if current_user.tier == "paid":
        return UsageInfo(
            used=0,
            limit=-1,           # -1 signals unlimited to the caller
            resets_at=next_week_start(),
            is_paid=True,
        )

    used = await _count_this_week(current_user.id, db)
    return UsageInfo(
        used=used,
        limit=settings.free_tier_weekly_limit,
        resets_at=next_week_start(),
        is_paid=False,
    )
