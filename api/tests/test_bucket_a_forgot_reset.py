"""Section 2.13 — Forgot/reset password end-to-end (PRODUCTION_TESTING.md)."""
from __future__ import annotations
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from api.models.user import User
from api.services import refresh_tokens as rt_module


pytestmark = pytest.mark.asyncio


async def _get_user(test_client: AsyncClient, email: str) -> User:
    session_factory = test_client.__test_session_factory__  # type: ignore[attr-defined]
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one()


async def test_forgot_password_returns_204_for_unknown_email(test_client: AsyncClient) -> None:
    r = await test_client.post(
        "/auth/forgot-password", json={"email": "ghost@example.com"}
    )
    # Per audit: always 204 regardless of whether the email is registered (enum
    # resistance).
    assert r.status_code in (200, 204), r.text


async def test_forgot_reset_full_flow_revokes_old_sessions(
    test_client: AsyncClient, monkeypatch
) -> None:
    # Pin the verification code so the test knows what to submit.
    monkeypatch.setattr("api.routes.auth._generate_verification_code", lambda: "424242")

    # Register + verify a user, log in to get a refresh token we can prove is revoked.
    email = "forgot@example.com"
    pw = "OldPasswordAbc!2026"
    await test_client.post("/auth/register", json={"email": email, "password": pw})

    session_factory = test_client.__test_session_factory__  # type: ignore[attr-defined]
    from sqlalchemy import update
    async with session_factory() as session:
        await session.execute(
            update(User).where(User.email == email).values(is_verified=True)
        )
        await session.commit()

    login = await test_client.post(
        "/auth/login", json={"email": email, "password": pw}
    )
    assert login.status_code == 200
    old_refresh = login.json()["refresh_token"]

    # Trigger forgot-password.
    r = await test_client.post(
        "/auth/forgot-password", json={"email": email}
    )
    assert r.status_code in (200, 204)

    # Hash should now exist on the user row.
    user = await _get_user(test_client, email)
    assert user.verification_token is not None

    # Submit the reset with a wrong code first → 400.
    bad = await test_client.post(
        "/auth/reset-password-with-email",
        json={"email": email, "code": "000000", "new_password": "NewPasswordAbc!2026"},
    )
    assert bad.status_code == 400, bad.text

    # Now submit the correct code → tokens reissued, old refresh revoked.
    new_pw = "NewPasswordAbc!2026"
    ok = await test_client.post(
        "/auth/reset-password-with-email",
        json={"email": email, "code": "424242", "new_password": new_pw},
    )
    assert ok.status_code == 200, ok.text

    # Old refresh should no longer work.
    bust = await test_client.post(
        "/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert bust.status_code == 401, bust.text

    # Login with new password works; old password does not.
    bad_login = await test_client.post(
        "/auth/login", json={"email": email, "password": pw}
    )
    assert bad_login.status_code == 401

    good_login = await test_client.post(
        "/auth/login", json={"email": email, "password": new_pw}
    )
    assert good_login.status_code == 200


async def test_reset_code_expires(test_client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr("api.routes.auth._generate_verification_code", lambda: "999999")

    email = "expiry@example.com"
    pw = "PasswordAbc!2026"
    await test_client.post("/auth/register", json={"email": email, "password": pw})

    # forgot-password to set the code
    await test_client.post("/auth/forgot-password", json={"email": email})

    # Manually expire the code
    session_factory = test_client.__test_session_factory__  # type: ignore[attr-defined]
    from sqlalchemy import update
    from datetime import datetime, timedelta, timezone
    async with session_factory() as session:
        await session.execute(
            update(User)
            .where(User.email == email)
            .values(verification_expires=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await session.commit()

    r = await test_client.post(
        "/auth/reset-password-with-email",
        json={"email": email, "code": "999999", "new_password": "NewPasswordAbc!2026"},
    )
    assert r.status_code == 400, r.text


async def test_reset_burns_code_after_too_many_wrong_attempts(
    test_client: AsyncClient, monkeypatch
) -> None:
    monkeypatch.setattr("api.routes.auth._generate_verification_code", lambda: "555555")

    email = "burn@example.com"
    pw = "PasswordAbc!2026"
    await test_client.post("/auth/register", json={"email": email, "password": pw})
    await test_client.post("/auth/forgot-password", json={"email": email})

    # 5 bad attempts → code wiped on the 5th.
    for _ in range(5):
        r = await test_client.post(
            "/auth/reset-password-with-email",
            json={"email": email, "code": "000000", "new_password": "NewPasswordAbc!2026"},
        )
        assert r.status_code == 400

    user = await _get_user(test_client, email)
    assert user.verification_token is None, "code should be burned after 5 wrong attempts"
