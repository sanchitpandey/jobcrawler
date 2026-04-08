"""
Tier enforcement integration tests.

Confirms that:
- Free users hit the weekly application + daily LLM limits.
- After upgrading via /billing/verify-payment, the same user is unlimited.

These tests use the same in-memory DB fixtures as the rest of the suite and
mock the Razorpay client so no network is touched.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import razorpay
from httpx import AsyncClient
from sqlalchemy import select

from api.config import get_settings

pytestmark = pytest.mark.asyncio


_JOB_BASE = {
    "company": "Acme AI",
    "title": "ML Engineer",
    "location": "Remote",
    "url": "https://example.com/job/",
    "description": "Build ML pipelines.",
}


def _fake_razorpay_client(order_id: str, plan: str = "monthly") -> MagicMock:
    fake = MagicMock()
    fake.order.create.return_value = {"id": order_id, "amount": 49900, "currency": "INR"}
    fake.order.fetch.return_value = {"id": order_id, "notes": {"plan": plan}}
    fake.utility.verify_payment_signature.return_value = True
    return fake


async def _track_job(client: AsyncClient, headers: dict, suffix: str) -> int:
    payload = {**_JOB_BASE, "company": f"Co-{suffix}", "url": f"https://ex.com/{suffix}"}
    resp = await client.post("/jobs", json=payload, headers=headers)
    return resp.status_code


# ── Free user weekly limit ────────────────────────────────────────────────────

async def test_free_user_rate_limited(
    test_client: AsyncClient, user_with_profile: dict
):
    """A free user is blocked at the 6th application in a calendar week."""
    headers = user_with_profile["headers"]
    for i in range(5):
        assert await _track_job(test_client, headers, f"f{i}") == 201
    assert await _track_job(test_client, headers, "f6") == 429


# ── Paid user has no rate limit ───────────────────────────────────────────────

async def test_paid_user_unlimited_after_upgrade(
    test_client: AsyncClient, user_with_profile: dict
):
    """
    Free user upgrades via /billing/verify-payment, then can track > 5 jobs
    in the same week without hitting 429.
    """
    headers = user_with_profile["headers"]

    # Use up the free quota
    for i in range(5):
        assert await _track_job(test_client, headers, f"pre{i}") == 201

    # 6th application — should now be blocked
    assert await _track_job(test_client, headers, "pre6") == 429

    # Upgrade via mocked Razorpay
    fake = _fake_razorpay_client("order_up", plan="monthly")
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        resp = await test_client.post(
            "/billing/verify-payment",
            json={
                "razorpay_order_id": "order_up",
                "razorpay_payment_id": "pay_up",
                "razorpay_signature": "sig_up",
            },
            headers=headers,
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"

    # Now the same user should be able to track more jobs
    for i in range(7):
        status = await _track_job(test_client, headers, f"post{i}")
        assert status == 201, f"Paid user blocked at job {i}: {status}"


# ── Free user daily LLM limit ────────────────────────────────────────────────

async def test_free_user_llm_limited(
    test_client: AsyncClient, user_with_profile: dict
):
    """A free user exceeding the daily LLM quota gets a 429 from /jobs/score-job."""
    from api.main import app
    from api.models.base import get_db as _get_db
    from api.models.llm_usage import LlmUsageLog
    from jose import jwt as jose_jwt

    settings = get_settings()
    limit = settings.free_tier_daily_llm_calls
    headers = user_with_profile["headers"]

    # Decode user_id from JWT
    access_token = headers["Authorization"].split(" ", 1)[1]
    payload = jose_jwt.decode(
        access_token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    user_id = payload["sub"]

    # Insert exactly `limit` LLM usage rows to exhaust the daily quota
    override = app.dependency_overrides.get(_get_db)
    async for session in override():
        for _ in range(limit):
            session.add(
                LlmUsageLog(
                    user_id=user_id,
                    tokens=10,
                    model="t",
                    call_type="score",
                )
            )
        await session.commit()
        break

    # Patch the underlying scorer so the test never actually calls an LLM
    with patch("api.routes.jobs.score_job", new_callable=AsyncMock):
        resp = await test_client.post(
            "/jobs/score-job",
            json={
                "id": "j1",
                "title": "ML Engineer",
                "company": "Acme",
                "description": "Build LLMs.",
            },
            headers=headers,
        )
    assert resp.status_code == 429
