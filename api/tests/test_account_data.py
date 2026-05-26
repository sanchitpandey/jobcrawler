"""Tests for GDPR / DPDP data-rights endpoints:

GET    /auth/me/export — right of access
DELETE /auth/me        — right to erasure
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from api.models.application import Application
from api.models.llm_usage import LlmUsageLog
from api.models.profile import Profile
from api.models.refresh_token import RefreshToken
from api.models.search_preference import SearchPreference
from api.models.subscription import Subscription
from api.models.user import User


# ── /auth/me/export ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_requires_auth(test_client):
    r = await test_client.get("/auth/me/export")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_export_returns_account_shell_for_fresh_user(test_client, auth_headers):
    r = await test_client.get("/auth/me/export", headers=auth_headers)
    assert r.status_code == 200, r.text
    archive = r.json()

    assert archive["export_format_version"] == 1
    assert "exported_at" in archive
    assert archive["account"]["email"] == "test@example.com"
    assert archive["account"]["tier"] in {"free", "paid"}
    # Fresh user has nothing else yet.
    assert archive["profile"] is None
    assert archive["applications"] == []
    assert archive["subscriptions"] == []
    assert archive["search_preference"] is None
    assert archive["llm_usage"] == []
    # The login that created the access token issued a refresh row.
    assert len(archive["sessions"]) >= 1
    assert "jti" in archive["sessions"][0]


@pytest.mark.asyncio
async def test_export_never_leaks_password_or_token_hashes(test_client, auth_headers):
    r = await test_client.get("/auth/me/export", headers=auth_headers)
    body = r.text
    # Hash columns must never reach the archive.
    assert "hashed_password" not in body
    assert "token_hash" not in body
    # Bcrypt prefix would also leak the verification token hash.
    assert "$2b$" not in body


@pytest.mark.asyncio
async def test_export_returns_attachment_filename(test_client, auth_headers):
    r = await test_client.get("/auth/me/export", headers=auth_headers)
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    assert ".json" in cd


@pytest.mark.asyncio
async def test_export_includes_profile_and_application_rows(
    test_client, user_with_profile
):
    headers = user_with_profile["headers"]

    # Track one application so the export has something user-owned beyond the profile.
    job = {
        "company": "Acme",
        "title": "ML Engineer",
        "location": "Remote",
        "url": "https://example.com/job/1",
        "description": "Build ML pipelines.",
        "fit_score": 82,
        "comp_est": "₹30L",
        "verdict": "strong_apply",
        "gaps": ["no kubernetes"],
    }
    track = await test_client.post("/jobs", json=job, headers=headers)
    assert track.status_code in (200, 201), track.text

    r = await test_client.get("/auth/me/export", headers=headers)
    assert r.status_code == 200
    archive = r.json()
    assert archive["profile"] is not None
    assert archive["profile"]["name"] == "Test User"
    assert len(archive["applications"]) == 1
    assert archive["applications"][0]["company"] == "Acme"


@pytest.mark.asyncio
async def test_export_throttled_after_burst(test_client, auth_headers):
    """The destructive bucket is 5/hr per user."""
    # First 5 succeed.
    for _ in range(5):
        r = await test_client.get("/auth/me/export", headers=auth_headers)
        assert r.status_code == 200, r.text
    # 6th hits the throttle.
    r = await test_client.get("/auth/me/export", headers=auth_headers)
    assert r.status_code == 429


# ── DELETE /auth/me ───────────────────────────────────────────────────────────

DELETE_BODY = {
    "password": "testpass-1234",
    "confirmation": "DELETE MY ACCOUNT",
}


@pytest.mark.asyncio
async def test_delete_requires_auth(test_client):
    r = await test_client.request("DELETE", "/auth/me", json=DELETE_BODY)
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_requires_confirmation_phrase(test_client, auth_headers):
    r = await test_client.request(
        "DELETE",
        "/auth/me",
        json={"password": "testpass-1234", "confirmation": "yes please"},
        headers=auth_headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_delete_requires_correct_password(test_client, auth_headers):
    r = await test_client.request(
        "DELETE",
        "/auth/me",
        json={"password": "WrongPassword99!", "confirmation": "DELETE MY ACCOUNT"},
        headers=auth_headers,
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_delete_removes_user_and_all_owned_rows(test_client, user_with_profile):
    headers = user_with_profile["headers"]
    session_factory = test_client.__test_session_factory__  # type: ignore[attr-defined]

    # Seed an application + an LLM usage row so we can prove cascade + explicit
    # delete both fire.
    job = {
        "company": "DeleteMe Inc",
        "title": "ML Engineer",
        "location": "Remote",
        "url": "https://example.com/job/2",
        "description": "Build ML pipelines.",
        "fit_score": 80,
        "comp_est": "₹30L",
        "verdict": "apply",
        "gaps": [],
    }
    track = await test_client.post("/jobs", json=job, headers=headers)
    assert track.status_code in (200, 201)

    async with session_factory() as s:
        user = (
            await s.execute(select(User).where(User.email == "test@example.com"))
        ).scalar_one()
        user_id = user.id
        s.add(
            LlmUsageLog(
                user_id=user_id, tokens=100, model="gpt-test", call_type="score"
            )
        )
        s.add(
            Subscription(
                user_id=user_id,
                plan="monthly",
                status="active",
                amount_paise=49900,
                currency="INR",
                starts_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            )
        )
        await s.commit()

    r = await test_client.request(
        "DELETE", "/auth/me", json=DELETE_BODY, headers=headers
    )
    assert r.status_code == 204, r.text

    # Every row that referenced the user must be gone.
    async with session_factory() as s:
        assert (
            await s.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none() is None
        assert (
            await s.execute(select(Profile).where(Profile.user_id == user_id))
        ).first() is None
        assert (
            await s.execute(select(Application).where(Application.user_id == user_id))
        ).first() is None
        assert (
            await s.execute(select(Subscription).where(Subscription.user_id == user_id))
        ).first() is None
        assert (
            await s.execute(
                select(SearchPreference).where(SearchPreference.user_id == user_id)
            )
        ).first() is None
        assert (
            await s.execute(
                select(RefreshToken).where(RefreshToken.user_id == user_id)
            )
        ).first() is None
        assert (
            await s.execute(
                select(LlmUsageLog).where(LlmUsageLog.user_id == user_id)
            )
        ).first() is None


@pytest.mark.asyncio
async def test_delete_invalidates_subsequent_access_token_use(test_client, registered_user):
    headers = {"Authorization": f"Bearer {registered_user['tokens']['access_token']}"}

    r = await test_client.request("DELETE", "/auth/me", json=DELETE_BODY, headers=headers)
    assert r.status_code == 204

    # The user row is gone; get_current_user must now 401 the same token.
    again = await test_client.get("/auth/me", headers=headers)
    assert again.status_code == 401


@pytest.mark.asyncio
async def test_delete_allows_re_registration_with_same_email(test_client, registered_user):
    headers = {"Authorization": f"Bearer {registered_user['tokens']['access_token']}"}

    r = await test_client.request("DELETE", "/auth/me", json=DELETE_BODY, headers=headers)
    assert r.status_code == 204

    # Email is freed up for re-registration.
    re_reg = await test_client.post(
        "/auth/register",
        json={"email": "test@example.com", "password": "freshpass-9876"},
    )
    assert re_reg.status_code == 202


@pytest.mark.asyncio
async def test_delete_throttled_after_burst(test_client, registered_user):
    """5 destructive attempts/hr — a brute-force confirmation guesser is stopped fast."""
    headers = {"Authorization": f"Bearer {registered_user['tokens']['access_token']}"}
    wrong = {"password": "WrongPassword99!", "confirmation": "DELETE MY ACCOUNT"}

    for _ in range(5):
        r = await test_client.request("DELETE", "/auth/me", json=wrong, headers=headers)
        assert r.status_code == 403, r.text
    r = await test_client.request("DELETE", "/auth/me", json=wrong, headers=headers)
    assert r.status_code == 429
