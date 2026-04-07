"""Integration tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


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
        "/auth/login", data={"username": "login@example.com", "password": "securepass1"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_wrong_password(test_client: AsyncClient, registered_user: dict):
    resp = await test_client.post(
        "/auth/login",
        data={"username": registered_user["email"], "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_user(test_client: AsyncClient):
    resp = await test_client.post(
        "/auth/login", data={"username": "ghost@example.com", "password": "securepass1"}
    )
    assert resp.status_code == 401


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
