"""
Integration tests for /billing routes — Razorpay client is fully mocked.

Strategy: patch `api.routes.billing._razorpay_client` so no network or
real signature verification occurs. Each test sets up the fake client's
return values and asserts on the resulting subscription/tier state.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import razorpay
from httpx import AsyncClient
from sqlalchemy import select

from api.models.subscription import Subscription
from api.models.user import User

pytestmark = pytest.mark.asyncio


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fake_client(
    order_id: str = "order_test123",
    plan_in_notes: str = "monthly",
    user_id: str = "",
    raise_signature: bool = False,
    raise_webhook_signature: bool = False,
):
    """Build a MagicMock that mimics razorpay.Client."""
    fake = MagicMock()
    # order.create
    fake.order.create.return_value = {
        "id": order_id,
        "amount": 49900,
        "currency": "INR",
        "notes": {"plan": plan_in_notes, "user_id": user_id},
    }
    # order.fetch
    fake.order.fetch.return_value = {
        "id": order_id,
        "notes": {"plan": plan_in_notes, "user_id": user_id},
    }
    # signature verification
    if raise_signature:
        fake.utility.verify_payment_signature.side_effect = (
            razorpay.errors.SignatureVerificationError("bad sig")
        )
    else:
        fake.utility.verify_payment_signature.return_value = True
    if raise_webhook_signature:
        fake.utility.verify_webhook_signature.side_effect = (
            razorpay.errors.SignatureVerificationError("bad webhook sig")
        )
    else:
        fake.utility.verify_webhook_signature.return_value = True
    return fake


async def _get_user_by_email(email: str) -> User:
    """Fetch a user from the test DB via the dependency override."""
    from api.main import app
    from api.models.base import get_db as _get_db

    override = app.dependency_overrides.get(_get_db)
    assert override is not None
    async for session in override():
        result = await session.execute(select(User).where(User.email == email))
        return result.scalar_one()
    raise RuntimeError("unreachable")


async def _list_subscriptions(user_id: str) -> list[Subscription]:
    from api.main import app
    from api.models.base import get_db as _get_db

    override = app.dependency_overrides.get(_get_db)
    assert override is not None
    async for session in override():
        result = await session.execute(
            select(Subscription).where(Subscription.user_id == user_id)
        )
        return list(result.scalars().all())
    raise RuntimeError("unreachable")


# ── /billing/create-order ─────────────────────────────────────────────────────

async def test_create_order_monthly(test_client: AsyncClient, auth_headers: dict):
    fake = _make_fake_client(order_id="order_mo1", plan_in_notes="monthly")
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        with patch("api.routes.billing.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                razorpay_key_id="rzp_test_xxx",
                razorpay_key_secret="secret",
                razorpay_webhook_secret="whsec",
            )
            resp = await test_client.post(
                "/billing/create-order",
                json={"plan": "monthly"},
                headers=auth_headers,
            )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["order_id"] == "order_mo1"
    assert data["amount"] == 49900
    assert data["currency"] == "INR"
    assert data["plan"] == "monthly"
    assert data["key_id"] == "rzp_test_xxx"
    fake.order.create.assert_called_once()


async def test_create_order_annual(test_client: AsyncClient, auth_headers: dict):
    fake = _make_fake_client(order_id="order_an1", plan_in_notes="annual")
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        with patch("api.routes.billing.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                razorpay_key_id="rzp_test_xxx",
                razorpay_key_secret="secret",
                razorpay_webhook_secret="whsec",
            )
            resp = await test_client.post(
                "/billing/create-order",
                json={"plan": "annual"},
                headers=auth_headers,
            )
    assert resp.status_code == 200
    data = resp.json()
    assert data["plan"] == "annual"
    assert data["amount"] == 499900
    # Verify the right amount was passed to razorpay
    call_args = fake.order.create.call_args[0][0]
    assert call_args["amount"] == 499900


async def test_create_order_requires_auth(test_client: AsyncClient):
    resp = await test_client.post("/billing/create-order", json={"plan": "monthly"})
    assert resp.status_code == 401


async def test_create_order_invalid_plan(
    test_client: AsyncClient, auth_headers: dict
):
    resp = await test_client.post(
        "/billing/create-order",
        json={"plan": "lifetime"},
        headers=auth_headers,
    )
    assert resp.status_code == 422  # pydantic validation


# ── /billing/verify-payment ───────────────────────────────────────────────────

async def test_verify_payment_success(
    test_client: AsyncClient, registered_user: dict, auth_headers: dict
):
    fake = _make_fake_client(order_id="order_v1", plan_in_notes="monthly")
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        resp = await test_client.post(
            "/billing/verify-payment",
            json={
                "razorpay_order_id": "order_v1",
                "razorpay_payment_id": "pay_v1",
                "razorpay_signature": "sig_v1",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert data["plan"] == "monthly"
    assert "expires_at" in data

    # User should be upgraded
    user = await _get_user_by_email(registered_user["email"])
    assert user.tier == "paid"

    # One subscription row should exist
    subs = await _list_subscriptions(user.id)
    assert len(subs) == 1
    assert subs[0].plan == "monthly"
    assert subs[0].razorpay_payment_id == "pay_v1"
    assert subs[0].amount_paise == 49900


async def test_verify_payment_invalid_signature(
    test_client: AsyncClient, auth_headers: dict
):
    fake = _make_fake_client(raise_signature=True)
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        resp = await test_client.post(
            "/billing/verify-payment",
            json={
                "razorpay_order_id": "order_bad",
                "razorpay_payment_id": "pay_bad",
                "razorpay_signature": "sig_bad",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 400
    assert "signature" in resp.json()["detail"].lower()


async def test_verify_payment_idempotent(
    test_client: AsyncClient, registered_user: dict, auth_headers: dict
):
    """Verifying the same payment twice should not create duplicate rows."""
    fake = _make_fake_client(order_id="order_idem", plan_in_notes="monthly")
    body = {
        "razorpay_order_id": "order_idem",
        "razorpay_payment_id": "pay_idem",
        "razorpay_signature": "sig_idem",
    }
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        resp1 = await test_client.post(
            "/billing/verify-payment", json=body, headers=auth_headers
        )
        resp2 = await test_client.post(
            "/billing/verify-payment", json=body, headers=auth_headers
        )

    assert resp1.status_code == 200
    assert resp1.json()["status"] == "success"
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_processed"

    user = await _get_user_by_email(registered_user["email"])
    subs = await _list_subscriptions(user.id)
    assert len(subs) == 1


async def test_verify_payment_annual_plan(
    test_client: AsyncClient, registered_user: dict, auth_headers: dict
):
    fake = _make_fake_client(order_id="order_an", plan_in_notes="annual")
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        resp = await test_client.post(
            "/billing/verify-payment",
            json={
                "razorpay_order_id": "order_an",
                "razorpay_payment_id": "pay_an",
                "razorpay_signature": "sig_an",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 200
    user = await _get_user_by_email(registered_user["email"])
    subs = await _list_subscriptions(user.id)
    assert subs[0].plan == "annual"
    assert subs[0].amount_paise == 499900
    # Annual subscription should expire ~365 days out
    delta = subs[0].expires_at - subs[0].starts_at
    assert 364 <= delta.days <= 366


# ── /billing/webhook ──────────────────────────────────────────────────────────

async def test_webhook_payment_captured(
    test_client: AsyncClient, registered_user: dict
):
    user = await _get_user_by_email(registered_user["email"])
    fake = _make_fake_client(
        order_id="order_wh", plan_in_notes="monthly", user_id=user.id
    )
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_wh",
                    "order_id": "order_wh",
                }
            }
        },
    }
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        with patch("api.routes.billing.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                razorpay_key_id="rzp_test_xxx",
                razorpay_key_secret="secret",
                razorpay_webhook_secret="whsec",
            )
            resp = await test_client.post(
                "/billing/webhook",
                json=payload,
                headers={"X-Razorpay-Signature": "fake_sig"},
            )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "processed"

    user = await _get_user_by_email(registered_user["email"])
    assert user.tier == "paid"
    subs = await _list_subscriptions(user.id)
    assert len(subs) == 1
    assert subs[0].razorpay_payment_id == "pay_wh"


async def test_webhook_invalid_signature(test_client: AsyncClient):
    fake = _make_fake_client(raise_webhook_signature=True)
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        with patch("api.routes.billing.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                razorpay_key_id="rzp_test_xxx",
                razorpay_key_secret="secret",
                razorpay_webhook_secret="whsec",
            )
            resp = await test_client.post(
                "/billing/webhook",
                json={"event": "payment.captured"},
                headers={"X-Razorpay-Signature": "bad"},
            )
    assert resp.status_code == 400


async def test_webhook_idempotent(
    test_client: AsyncClient, registered_user: dict
):
    """Replaying a webhook for the same payment_id is a no-op."""
    user = await _get_user_by_email(registered_user["email"])
    fake = _make_fake_client(
        order_id="order_wh2", plan_in_notes="monthly", user_id=user.id
    )
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": "pay_wh2", "order_id": "order_wh2"}
            }
        },
    }
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        with patch("api.routes.billing.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                razorpay_key_id="rzp_test_xxx",
                razorpay_key_secret="secret",
                razorpay_webhook_secret="whsec",
            )
            await test_client.post(
                "/billing/webhook",
                json=payload,
                headers={"X-Razorpay-Signature": "sig"},
            )
            resp2 = await test_client.post(
                "/billing/webhook",
                json=payload,
                headers={"X-Razorpay-Signature": "sig"},
            )
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "already_processed"
    subs = await _list_subscriptions(user.id)
    assert len(subs) == 1


# ── /billing/status ───────────────────────────────────────────────────────────

async def test_billing_status_free(test_client: AsyncClient, auth_headers: dict):
    resp = await test_client.get("/billing/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["plan"] is None
    assert data["expires_at"] is None
    assert data["is_active"] is False


async def test_billing_status_paid(
    test_client: AsyncClient, registered_user: dict, auth_headers: dict
):
    """After verify-payment succeeds, /status should report paid + active."""
    fake = _make_fake_client(order_id="order_st", plan_in_notes="monthly")
    with patch("api.routes.billing._razorpay_client", return_value=fake):
        await test_client.post(
            "/billing/verify-payment",
            json={
                "razorpay_order_id": "order_st",
                "razorpay_payment_id": "pay_st",
                "razorpay_signature": "sig_st",
            },
            headers=auth_headers,
        )

    resp = await test_client.get("/billing/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "paid"
    assert data["plan"] == "monthly"
    assert data["is_active"] is True
    assert data["expires_at"] is not None


async def test_billing_status_expired_downgrades(
    test_client: AsyncClient, registered_user: dict, auth_headers: dict
):
    """Expired subscription auto-downgrades user to free on /status read."""
    from api.main import app
    from api.models.base import get_db as _get_db

    user = await _get_user_by_email(registered_user["email"])
    # Insert an already-expired subscription manually
    override = app.dependency_overrides.get(_get_db)
    async for session in override():
        past = datetime.now(timezone.utc) - timedelta(days=10)
        session.add(
            Subscription(
                user_id=user.id,
                plan="monthly",
                status="active",
                razorpay_order_id="order_exp",
                razorpay_payment_id="pay_exp",
                amount_paise=49900,
                currency="INR",
                starts_at=past - timedelta(days=30),
                expires_at=past,
            )
        )
        result = await session.execute(select(User).where(User.id == user.id))
        u = result.scalar_one()
        u.tier = "paid"
        await session.commit()
        break

    resp = await test_client.get("/billing/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tier"] == "free"
    assert data["is_active"] is False

    user_after = await _get_user_by_email(registered_user["email"])
    assert user_after.tier == "free"


async def test_billing_status_requires_auth(test_client: AsyncClient):
    resp = await test_client.get("/billing/status")
    assert resp.status_code == 401
