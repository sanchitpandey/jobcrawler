"""
Integration tests for rate limiting.

These complement the unit tests in test_rate_limit.py by exercising the
real HTTP endpoints against the in-memory test database.
"""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_JOB_BASE = {
    "company": "Acme AI",
    "title": "ML Engineer",
    "location": "Remote",
    "url": "https://example.com/job/",
    "description": "Build ML pipelines.",
}


async def _track_job(client: AsyncClient, headers: dict, suffix: str) -> int:
    """Track a uniquely-identified job; return the HTTP status code."""
    payload = {**_JOB_BASE, "company": f"Company-{suffix}", "url": f"https://example.com/job/{suffix}"}
    resp = await client.post("/jobs", json=payload, headers=headers)
    return resp.status_code


# ── Free tier weekly apply limit ──────────────────────────────────────────────

async def test_free_tier_limit(test_client: AsyncClient, user_with_profile: dict):
    """Free tier: 6th application in a week returns 429."""
    headers = user_with_profile["headers"]

    for i in range(5):
        status = await _track_job(test_client, headers, str(i))
        assert status == 201, f"Expected 201 on job {i}, got {status}"

    status = await _track_job(test_client, headers, "6")
    assert status == 429


async def test_free_tier_429_includes_retry_after(
    test_client: AsyncClient, user_with_profile: dict
):
    """The 429 response includes a Retry-After header."""
    headers = user_with_profile["headers"]
    for i in range(5):
        await _track_job(test_client, headers, f"ra-{i}")

    resp = await test_client.post(
        "/jobs",
        json={**_JOB_BASE, "company": "Overflow", "url": "https://example.com/overflow"},
        headers=headers,
    )
    assert resp.status_code == 429
    assert "retry-after" in {k.lower() for k in resp.headers}


async def test_paid_tier_unlimited(test_client: AsyncClient):
    """Paid-tier users can track more than 5 jobs without hitting a limit."""
    from api.main import app
    from api.models.base import get_db as _get_db
    from api.models.user import User
    from sqlalchemy import select

    reg = await test_client.post(
        "/auth/register",
        json={"email": "paid@example.com", "password": "paidpass1"},
    )
    assert reg.status_code == 201
    token = reg.json()["access_token"]
    paid_headers = {"Authorization": f"Bearer {token}"}

    # Create profile for paid user
    await test_client.post(
        "/profile",
        json={"name": "Paid User", "college": "MIT"},
        headers=paid_headers,
    )

    # Promote to paid tier via the test DB override
    override = app.dependency_overrides.get(_get_db)
    if override:
        async for session in override():
            result = await session.execute(
                select(User).where(User.email == "paid@example.com")
            )
            user = result.scalar_one()
            user.tier = "paid"
            await session.commit()
            break

    # Track 7 jobs — all should succeed for paid user
    for i in range(7):
        status = await _track_job(test_client, paid_headers, f"paid-{i}")
        assert status == 201, f"Paid user blocked on job {i}"


# ── LLM daily limit ───────────────────────────────────────────────────────────

async def test_llm_daily_limit_blocks_score_job(
    test_client: AsyncClient, user_with_profile: dict
):
    """
    When a free user exhausts their daily LLM quota, /jobs/score-job returns 429.
    We simulate exhaustion by inserting LLmUsageLogs directly.
    """
    from api.models.base import get_db as _get_db
    from api.models.llm_usage import LlmUsageLog
    from api.config import get_settings

    settings = get_settings()
    limit = settings.free_tier_daily_llm_calls

    # Get the user id from the profile
    headers = user_with_profile["headers"]
    profile_resp = await test_client.get("/profile", headers=headers)
    assert profile_resp.status_code == 200

    # Decode user id from JWT
    from jose import jwt as jose_jwt
    from api.main import app
    access_token = headers["Authorization"].split(" ", 1)[1]
    payload = jose_jwt.decode(
        access_token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    user_id = payload["sub"]

    # Insert log rows to exhaust the daily limit
    override = app.dependency_overrides.get(_get_db)
    if override:
        async for session in override():
            for _ in range(limit):
                session.add(LlmUsageLog(
                    user_id=user_id,
                    tokens=100,
                    model="test-model",
                    call_type="score",
                ))
            await session.commit()
            break

    # Now the score-job call should be blocked
    from unittest.mock import AsyncMock, patch
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
