"""Integration tests for authentication endpoints."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from api.main import app
from api.models.base import get_db
from api.models.user import User

pytestmark = pytest.mark.asyncio


async def _get_user_by_email(email: str) -> User:
    override = app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one()
    finally:
        await agen.aclose()


# ── POST /auth/register ───────────────────────────────────────────────────────

async def test_register_success(test_client: AsyncClient):
    resp = await test_client.post(
        "/auth/register", json={"email": "new@example.com", "password": "securepass1"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_register_stores_email_verification_state(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    from api.routes import auth

    monkeypatch.setattr(auth, "_generate_verification_code", lambda: "123456")
    resp = await test_client.post(
        "/auth/register", json={"email": "verify@example.com", "password": "securepass1"}
    )
    assert resp.status_code == 201

    user = await _get_user_by_email("verify@example.com")
    assert user.is_verified is False
    assert user.verification_token is not None
    assert user.verification_token != "123456"
    assert user.verification_expires is not None
    # SQLite returns naive datetimes — normalize before comparing.
    expires = user.verification_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    assert expires > datetime.now(timezone.utc)


async def test_register_duplicate_email(test_client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "securepass1"}
    r1 = await test_client.post("/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await test_client.post("/auth/register", json=payload)
    assert r2.status_code == 409


async def test_register_weak_password(test_client: AsyncClient):
    resp = await test_client.post(
        "/auth/register", json={"email": "weak@example.com", "password": "short"}
    )
    assert resp.status_code == 422


async def test_register_invalid_email(test_client: AsyncClient):
    resp = await test_client.post(
        "/auth/register", json={"email": "not-an-email", "password": "securepass1"}
    )
    assert resp.status_code == 422


# ── POST /auth/login ──────────────────────────────────────────────────────────

async def test_login_success(test_client: AsyncClient):
    await test_client.post(
        "/auth/register", json={"email": "login@example.com", "password": "securepass1"}
    )
    resp = await test_client.post(
        "/auth/login", json={"email": "login@example.com", "password": "securepass1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_wrong_password(test_client: AsyncClient, registered_user: dict):
    resp = await test_client.post(
        "/auth/login",
        json={"email": registered_user["email"], "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_user(test_client: AsyncClient):
    resp = await test_client.post(
        "/auth/login", json={"email": "ghost@example.com", "password": "securepass1"}
    )
    assert resp.status_code == 401


async def test_login_not_blocked_by_unverified_email(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    from api.routes import auth

    monkeypatch.setattr(auth, "_generate_verification_code", lambda: "123456")
    register_resp = await test_client.post(
        "/auth/register", json={"email": "pending@example.com", "password": "securepass1"}
    )
    assert register_resp.status_code == 201

    me_resp = await test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {register_resp.json()['access_token']}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["is_verified"] is False


# ── POST /auth/refresh ────────────────────────────────────────────────────────

async def test_refresh_token(test_client: AsyncClient, registered_user: dict):
    refresh_token = registered_user["tokens"]["refresh_token"]
    resp = await test_client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_refresh_with_access_token_fails(
    test_client: AsyncClient, registered_user: dict
):
    """Access token must not be accepted as a refresh token."""
    access_token = registered_user["tokens"]["access_token"]
    resp = await test_client.post(
        "/auth/refresh", json={"refresh_token": access_token}
    )
    assert resp.status_code == 401


async def test_verify_email_success(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    from api.routes import auth

    monkeypatch.setattr(auth, "_generate_verification_code", lambda: "654321")
    register_resp = await test_client.post(
        "/auth/register", json={"email": "confirm@example.com", "password": "securepass1"}
    )
    assert register_resp.status_code == 201

    headers = {"Authorization": f"Bearer {register_resp.json()['access_token']}"}
    verify_resp = await test_client.post(
        "/auth/verify-email", json={"code": "654321"}, headers=headers
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_verified"] is True

    user = await _get_user_by_email("confirm@example.com")
    assert user.is_verified is True
    assert user.verification_token is None
    assert user.verification_expires is None


async def test_verify_email_rejects_invalid_code(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    from api.routes import auth

    monkeypatch.setattr(auth, "_generate_verification_code", lambda: "654321")
    register_resp = await test_client.post(
        "/auth/register", json={"email": "invalidcode@example.com", "password": "securepass1"}
    )
    headers = {"Authorization": f"Bearer {register_resp.json()['access_token']}"}

    verify_resp = await test_client.post(
        "/auth/verify-email", json={"code": "000000"}, headers=headers
    )
    assert verify_resp.status_code == 400
    assert verify_resp.json()["detail"] == "Invalid verification code."


async def test_verify_email_rejects_expired_code(
    test_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    from api.routes import auth

    monkeypatch.setattr(auth, "_generate_verification_code", lambda: "654321")
    register_resp = await test_client.post(
        "/auth/register", json={"email": "expired@example.com", "password": "securepass1"}
    )
    assert register_resp.status_code == 201

    override = app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        result = await session.execute(select(User).where(User.email == "expired@example.com"))
        user = result.scalar_one()
        user.verification_expires = datetime.now(timezone.utc) - timedelta(minutes=1)
        await session.commit()
    finally:
        await agen.aclose()

    headers = {"Authorization": f"Bearer {register_resp.json()['access_token']}"}
    verify_resp = await test_client.post(
        "/auth/verify-email", json={"code": "654321"}, headers=headers
    )
    assert verify_resp.status_code == 400
    assert verify_resp.json()["detail"] == "Verification code expired or unavailable."


# ── Protected route behaviour ─────────────────────────────────────────────────

async def test_protected_route_no_token(test_client: AsyncClient):
    resp = await test_client.get("/profile")
    assert resp.status_code == 401


async def test_protected_route_with_token(
    test_client: AsyncClient, registered_user: dict
):
    # Profile doesn't exist yet — expect 404, not 401
    headers = {"Authorization": f"Bearer {registered_user['tokens']['access_token']}"}
    resp = await test_client.get("/profile", headers=headers)
    assert resp.status_code == 404
