"""
Shared pytest fixtures for integration tests.

Every async fixture creates a fresh in-memory SQLite database so tests are
fully isolated with no shared state between them.
"""

import os
import sys
from unittest.mock import MagicMock

# Audit fix #14: JWT_SECRET_KEY is now required (no committed default), so
# inject one before api.config is imported by api.main below.
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "test-only-secret-key-must-be-at-least-32-characters-long",
)

# razorpay==1.4.2 imports pkg_resources (setuptools) only to read its own version.
# Stub it out so the test suite runs on Python 3.12 without setuptools installed.
if "pkg_resources" not in sys.modules:
    sys.modules["pkg_resources"] = MagicMock()

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.main import app
from api.models import Base  # noqa: F401 — registers all models on metadata
from api.models.base import get_db

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def test_client() -> AsyncClient:
    """
    httpx.AsyncClient wired to the FastAPI app with a clean in-memory SQLite
    database.  Dependency-overrides are cleared after each test.

    The session factory is attached to the client so fixtures (e.g.
    ``registered_user``) can open ad-hoc sessions against the same DB.
    """
    engine = create_async_engine(TEST_DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )

    async def _override_get_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        client.__test_session_factory__ = session_factory  # type: ignore[attr-defined]
        yield client

    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
def _reset_auth_throttle():
    """Clear the in-memory auth-throttle counters between tests."""
    from api.middleware import auth_throttle
    auth_throttle.reset_for_tests()
    yield
    auth_throttle.reset_for_tests()


@pytest_asyncio.fixture()
async def registered_user(test_client: AsyncClient) -> dict:
    """Register a fresh user and log them in. Returns email, password, tokens.

    Marks the user as verified so endpoints gated by ``require_verified_user``
    (audit fix #16) are reachable in the default fixture. Tests that explicitly
    exercise verification flow construct their own users.
    """
    email = "test@example.com"
    password = "testpass-1234"   # ≥12 chars per the hardened policy
    reg = await test_client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert reg.status_code == 202, reg.text

    # Flip is_verified directly so tests don't have to consume a real code.
    from sqlalchemy import update
    from api.models.user import User
    session_factory = test_client.__test_session_factory__  # type: ignore[attr-defined]
    async with session_factory() as session:
        await session.execute(update(User).where(User.email == email).values(is_verified=True))
        await session.commit()

    login = await test_client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert login.status_code == 200, login.text
    return {"email": email, "password": password, "tokens": login.json()}


@pytest_asyncio.fixture()
async def auth_headers(registered_user: dict) -> dict:
    """Authorization headers for the registered test user."""
    return {"Authorization": f"Bearer {registered_user['tokens']['access_token']}"}


@pytest_asyncio.fixture()
async def user_with_profile(test_client: AsyncClient, registered_user: dict) -> dict:
    """Registered user who also has a complete profile."""
    headers = {"Authorization": f"Bearer {registered_user['tokens']['access_token']}"}
    payload = {
        "name": "Test User",
        "email": "test@example.com",
        "phone": "+91-9999999999",
        "college": "BITS Pilani",
        "degree": "B.E. EIE",
        "graduation_year": "2026",
        "cgpa": "7.15",
        "notice_period": "Available immediately",
        "total_experience": "1 year",
        "work_authorization": "Yes",
        "willing_to_relocate": "Yes",
        "willing_to_travel": "Yes",
        "sponsorship_required": "No",
        "skills": {"python_years": "3", "ml_years": "2"},
        "eeo": {"gender": "male", "ethnicity": "asian"},
        "candidate_summary": "Final-year student at BITS Pilani.",
        "preferred_roles": "ML Engineer, NLP Engineer",
        "target_locations": "Bengaluru, Remote",
    }
    resp = await test_client.post("/profile", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return {"user": registered_user, "profile": resp.json(), "headers": headers}
