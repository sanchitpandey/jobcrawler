"""Tests for api/middleware/usage.py — pure logic, no real DB."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from api.middleware.usage import (
    month_start,
    record_usage,
    get_token_usage,
    TokenUsageInfo,
)


# ── month_start ───────────────────────────────────────────────────────────────

def test_month_start_day_is_one():
    ms = month_start()
    assert ms.day == 1


def test_month_start_time_is_midnight():
    ms = month_start()
    assert ms.hour == 0
    assert ms.minute == 0
    assert ms.second == 0
    assert ms.microsecond == 0


def test_month_start_is_utc():
    ms = month_start()
    assert ms.tzinfo == timezone.utc


def test_month_start_not_in_future():
    assert month_start() <= datetime.now(timezone.utc)


# ── record_usage ──────────────────────────────────────────────────────────────

def _make_db_ok() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_record_usage_adds_log_row():
    db = _make_db_ok()
    await record_usage(user_id="u1", tokens=123, model="llama-3.3-70b", call_type="score", db=db)
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_usage_does_not_raise_on_db_error():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock(side_effect=RuntimeError("connection lost"))
    db.rollback = AsyncMock()
    # Must not propagate the exception
    await record_usage(user_id="u1", tokens=50, model="x", call_type="score", db=db)
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_usage_log_has_correct_fields():
    db = _make_db_ok()
    captured = []
    db.add = lambda obj: captured.append(obj)

    await record_usage(user_id="u42", tokens=500, model="gemini", call_type="form_fill", db=db)

    assert len(captured) == 1
    log = captured[0]
    assert log.user_id == "u42"
    assert log.tokens == 500
    assert log.model == "gemini"
    assert log.call_type == "form_fill"


# ── get_token_usage ───────────────────────────────────────────────────────────

def _make_user(user_id: str = "user-1") -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _make_db_with_result(total_tokens, call_count) -> AsyncMock:
    row = MagicMock()
    row.__getitem__ = lambda self, i: (total_tokens if i == 0 else call_count)
    result = MagicMock()
    result.one.return_value = row
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_get_token_usage_returns_correct_totals():
    user = _make_user()
    db = _make_db_with_result(total_tokens=1500, call_count=4)
    info = await get_token_usage(current_user=user, db=db)
    assert info.total_tokens == 1500
    assert info.call_count == 4


@pytest.mark.asyncio
async def test_get_token_usage_period_start_is_month_start():
    user = _make_user()
    db = _make_db_with_result(0, 0)
    info = await get_token_usage(current_user=user, db=db)
    assert info.period_start == month_start()


@pytest.mark.asyncio
async def test_get_token_usage_zero_when_no_calls():
    user = _make_user()
    db = _make_db_with_result(None, 0)
    info = await get_token_usage(current_user=user, db=db)
    assert info.total_tokens == 0
    assert info.call_count == 0


@pytest.mark.asyncio
async def test_get_token_usage_queries_db():
    user = _make_user()
    db = _make_db_with_result(100, 1)
    await get_token_usage(current_user=user, db=db)
    db.execute.assert_awaited_once()


# ── TokenUsageInfo ────────────────────────────────────────────────────────────

def test_token_usage_info_slots():
    info = TokenUsageInfo(total_tokens=300, call_count=2, period_start=month_start())
    assert info.total_tokens == 300
    assert info.call_count == 2
    assert info.period_start.day == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
