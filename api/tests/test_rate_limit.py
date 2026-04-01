"""Tests for api/middleware/rate_limit.py — pure logic, no DB."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from api.middleware.rate_limit import (
    week_start,
    next_week_start,
    retry_after_seconds,
    check_apply_limit,
    get_usage,
    UsageInfo,
)


# ── week_start / next_week_start ──────────────────────────────────────────────

def test_week_start_is_monday():
    ws = week_start()
    assert ws.weekday() == 0          # Monday
    assert ws.hour == 0
    assert ws.minute == 0
    assert ws.second == 0
    assert ws.microsecond == 0
    assert ws.tzinfo == timezone.utc


def test_next_week_start_is_seven_days_later():
    assert next_week_start() == week_start() + timedelta(weeks=1)


def test_week_start_is_not_in_future():
    assert week_start() <= datetime.now(timezone.utc)


def test_next_week_start_is_in_future():
    assert next_week_start() > datetime.now(timezone.utc)


# ── retry_after_seconds ───────────────────────────────────────────────────────

def test_retry_after_seconds_positive():
    secs = retry_after_seconds()
    assert secs >= 1


def test_retry_after_seconds_at_most_one_week():
    assert retry_after_seconds() <= 7 * 24 * 3600


# ── check_apply_limit ─────────────────────────────────────────────────────────

def _make_user(tier: str) -> MagicMock:
    user = MagicMock()
    user.id = "user-1"
    user.tier = tier
    return user


def _make_db(count: int) -> AsyncMock:
    scalar = MagicMock()
    scalar.scalar_one.return_value = count
    db = AsyncMock()
    db.execute = AsyncMock(return_value=scalar)
    return db


@pytest.mark.asyncio
async def test_paid_user_always_passes():
    user = _make_user("paid")
    db = AsyncMock()
    # Should return immediately — no DB query
    await check_apply_limit(current_user=user, db=db)
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_free_user_under_limit_passes():
    user = _make_user("free")
    db = _make_db(count=3)  # 3 < 5
    await check_apply_limit(current_user=user, db=db)  # no exception


@pytest.mark.asyncio
async def test_free_user_at_limit_raises_429():
    from fastapi import HTTPException
    user = _make_user("free")
    db = _make_db(count=5)  # == 5 (limit)
    with pytest.raises(HTTPException) as exc_info:
        await check_apply_limit(current_user=user, db=db)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_free_user_over_limit_raises_429():
    from fastapi import HTTPException
    user = _make_user("free")
    db = _make_db(count=7)
    with pytest.raises(HTTPException) as exc_info:
        await check_apply_limit(current_user=user, db=db)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_429_detail_mentions_limit():
    from fastapi import HTTPException
    user = _make_user("free")
    db = _make_db(count=5)
    with pytest.raises(HTTPException) as exc_info:
        await check_apply_limit(current_user=user, db=db)
    assert "5" in exc_info.value.detail
    assert "paid" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_free_user_zero_used_passes():
    user = _make_user("free")
    db = _make_db(count=0)
    await check_apply_limit(current_user=user, db=db)  # no exception


# ── get_usage ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_usage_paid_returns_unlimited():
    user = _make_user("paid")
    db = AsyncMock()
    info = await get_usage(current_user=user, db=db)
    assert info.is_paid is True
    assert info.limit == -1
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_usage_free_returns_count():
    user = _make_user("free")
    db = _make_db(count=3)
    info = await get_usage(current_user=user, db=db)
    assert info.is_paid is False
    assert info.used == 3
    assert info.limit == 5
    assert info.resets_at == next_week_start()


@pytest.mark.asyncio
async def test_get_usage_free_at_zero():
    user = _make_user("free")
    db = _make_db(count=0)
    info = await get_usage(current_user=user, db=db)
    assert info.used == 0
    assert info.limit == 5


@pytest.mark.asyncio
async def test_get_usage_free_exhausted():
    user = _make_user("free")
    db = _make_db(count=5)
    info = await get_usage(current_user=user, db=db)
    assert info.used == 5
    assert info.used >= info.limit


# ── UsageInfo ─────────────────────────────────────────────────────────────────

def test_usage_info_slots():
    info = UsageInfo(used=2, limit=5, resets_at=next_week_start(), is_paid=False)
    assert info.used == 2
    assert info.limit == 5
    assert info.is_paid is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
