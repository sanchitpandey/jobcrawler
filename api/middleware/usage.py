"""
LLM token usage tracking per user.

Usage
-----
After any LLM call, record the token count::

    text, tokens = await chat_with_tokens(prompt)
    await record_usage(user_id=user.id, tokens=tokens, model="llama-3.3-70b",
                       call_type="score", db=db)

Inject ``get_token_usage`` as a dependency to read the current user's
monthly token stats (e.g. for a billing dashboard)::

    @router.get("/usage/tokens")
    async def token_usage(info=Depends(get_token_usage)):
        ...
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.base import get_db
from api.models.llm_usage import LlmUsageLog
from api.models.user import User
from api.routes.auth import get_current_user


# ── helpers ───────────────────────────────────────────────────────────────────

def month_start() -> datetime:
    """First moment of the current UTC month."""
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ── record ────────────────────────────────────────────────────────────────────

async def record_usage(
    *,
    user_id: str,
    tokens: int,
    model: str,
    call_type: str,
    db: AsyncSession,
) -> None:
    """Persist one LLM call's token usage.  Fire-and-forget: does not raise."""
    try:
        db.add(
            LlmUsageLog(
                user_id=user_id,
                tokens=tokens,
                model=model,
                call_type=call_type,
            )
        )
        await db.commit()
    except Exception:  # pragma: no cover  # billing log must never break the caller
        await db.rollback()


# ── query ─────────────────────────────────────────────────────────────────────

class TokenUsageInfo:
    """Monthly token usage snapshot for a user."""

    __slots__ = ("total_tokens", "call_count", "period_start")

    def __init__(self, total_tokens: int, call_count: int, period_start: datetime) -> None:
        self.total_tokens = total_tokens
        self.call_count = call_count
        self.period_start = period_start


async def get_token_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TokenUsageInfo:
    """Dependency — returns the current user's token usage for the current calendar month."""
    period = month_start()
    result = await db.execute(
        select(func.sum(LlmUsageLog.tokens), func.count())
        .where(
            LlmUsageLog.user_id == current_user.id,
            LlmUsageLog.created_at >= period,
        )
    )
    row = result.one()
    return TokenUsageInfo(
        total_tokens=int(row[0] or 0),
        call_count=int(row[1] or 0),
        period_start=period,
    )
