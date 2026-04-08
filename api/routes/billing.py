"""
Billing routes — Razorpay payment integration.

POST /billing/create-order   — create a Razorpay order for a plan
POST /billing/verify-payment — verify signature and activate subscription
POST /billing/webhook        — Razorpay server-to-server callback
GET  /billing/status         — current tier / plan info
"""

from datetime import datetime, timedelta, timezone
from typing import Literal

import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.logger import get_logger
from api.models.base import get_db
from api.models.subscription import Subscription
from api.models.user import User
from api.routes.auth import get_current_user

router = APIRouter(prefix="/billing", tags=["billing"])
log = get_logger(__name__)


# ── Plan config ────────────────────────────────────────────────────────────────

PLANS: dict[str, dict] = {
    "monthly": {"amount": 49900, "label": "Monthly", "days": 30},
    "annual": {"amount": 499900, "label": "Annual", "days": 365},
}


def _razorpay_client() -> razorpay.Client:
    settings = get_settings()
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateOrderRequest(BaseModel):
    plan: Literal["monthly", "annual"]


class CreateOrderResponse(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str
    plan: str


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class VerifyPaymentResponse(BaseModel):
    status: str
    plan: str
    expires_at: datetime


class BillingStatusResponse(BaseModel):
    tier: str
    plan: str | None = None
    expires_at: datetime | None = None
    is_active: bool


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _activate_subscription(
    db: AsyncSession,
    user: User,
    plan_key: str,
    razorpay_order_id: str,
    razorpay_payment_id: str,
) -> Subscription:
    """Create a subscription row and upgrade the user tier."""
    plan = PLANS[plan_key]
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id,
        plan=plan_key,
        status="active",
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        amount_paise=plan["amount"],
        currency="INR",
        starts_at=now,
        expires_at=now + timedelta(days=plan["days"]),
    )
    db.add(sub)
    user.tier = "paid"
    await db.commit()
    await db.refresh(sub)
    return sub


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/create-order", response_model=CreateOrderResponse)
async def create_order(
    req: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
) -> CreateOrderResponse:
    """Create a Razorpay order for the selected plan."""
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise HTTPException(status_code=503, detail="Payment gateway not configured")

    plan = PLANS[req.plan]
    client = _razorpay_client()

    try:
        order = client.order.create({
            "amount": plan["amount"],
            "currency": "INR",
            "receipt": f"jc_{current_user.id[:8]}_{req.plan}",
            "notes": {"user_id": current_user.id, "plan": req.plan},
        })
    except Exception as exc:
        log.error("razorpay order create failed", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail="Failed to create order")

    log.info(
        "razorpay order created",
        extra={"user_id": current_user.id, "plan": req.plan, "order_id": order["id"]},
    )
    return CreateOrderResponse(
        order_id=order["id"],
        amount=plan["amount"],
        currency="INR",
        key_id=settings.razorpay_key_id,
        plan=req.plan,
    )


@router.post("/verify-payment", response_model=VerifyPaymentResponse)
async def verify_payment(
    req: VerifyPaymentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> VerifyPaymentResponse:
    """Verify Razorpay payment signature and activate subscription."""
    client = _razorpay_client()

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": req.razorpay_order_id,
            "razorpay_payment_id": req.razorpay_payment_id,
            "razorpay_signature": req.razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        log.warning(
            "invalid payment signature",
            extra={"user_id": current_user.id, "order_id": req.razorpay_order_id},
        )
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Idempotency: if we've already processed this payment, return existing.
    existing = await db.execute(
        select(Subscription).where(
            Subscription.razorpay_payment_id == req.razorpay_payment_id
        )
    )
    sub = existing.scalar_one_or_none()
    if sub:
        return VerifyPaymentResponse(
            status="already_processed",
            plan=sub.plan,
            expires_at=sub.expires_at,
        )

    # Determine plan from order notes
    try:
        order = client.order.fetch(req.razorpay_order_id)
    except Exception as exc:
        log.error("razorpay order fetch failed", extra={"error": str(exc)})
        raise HTTPException(status_code=502, detail="Failed to fetch order")

    plan_key = order.get("notes", {}).get("plan", "monthly")
    if plan_key not in PLANS:
        raise HTTPException(status_code=400, detail=f"Unknown plan: {plan_key}")

    sub = await _activate_subscription(
        db,
        current_user,
        plan_key,
        req.razorpay_order_id,
        req.razorpay_payment_id,
    )

    log.info(
        "subscription activated",
        extra={"user_id": current_user.id, "plan": plan_key, "expires_at": sub.expires_at.isoformat()},
    )
    return VerifyPaymentResponse(
        status="success",
        plan=plan_key,
        expires_at=sub.expires_at,
    )


@router.post("/webhook")
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Razorpay server-to-server webhook (payment.captured, etc.)."""
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    client = _razorpay_client()
    try:
        client.utility.verify_webhook_signature(
            body.decode(), signature, settings.razorpay_webhook_secret
        )
    except razorpay.errors.SignatureVerificationError:
        log.warning("invalid webhook signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")
    log.info("razorpay webhook received", extra={"event": event})

    if event == "payment.captured":
        entity = payload["payload"]["payment"]["entity"]
        payment_id = entity["id"]
        order_id = entity.get("order_id")

        # Idempotent: skip if already processed
        existing = await db.execute(
            select(Subscription).where(
                Subscription.razorpay_payment_id == payment_id
            )
        )
        if existing.scalar_one_or_none():
            return {"status": "already_processed"}

        # Need user_id and plan — fetch from order notes
        try:
            order = client.order.fetch(order_id)
        except Exception as exc:
            log.error("webhook order fetch failed", extra={"error": str(exc)})
            raise HTTPException(status_code=502, detail="Failed to fetch order")

        notes = order.get("notes", {}) or {}
        user_id = notes.get("user_id")
        plan_key = notes.get("plan", "monthly")
        if not user_id or plan_key not in PLANS:
            log.warning("webhook missing notes", extra={"order_id": order_id})
            return {"status": "ignored"}

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            log.warning("webhook user not found", extra={"user_id": user_id})
            return {"status": "ignored"}

        await _activate_subscription(db, user, plan_key, order_id, payment_id)
        return {"status": "processed"}

    return {"status": "ok"}


@router.get("/status", response_model=BillingStatusResponse)
async def billing_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BillingStatusResponse:
    """Return current billing/tier information; auto-downgrade if expired."""
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == current_user.id,
            Subscription.status == "active",
        )
        .order_by(Subscription.expires_at.desc())
        .limit(1)
    )
    sub = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    # SQLite returns naive datetimes; normalize to UTC for comparison.
    sub_expires = sub.expires_at if sub else None
    if sub_expires is not None and sub_expires.tzinfo is None:
        sub_expires = sub_expires.replace(tzinfo=timezone.utc)

    if sub and sub_expires and sub_expires > now:
        if current_user.tier != "paid":
            current_user.tier = "paid"
            await db.commit()
        return BillingStatusResponse(
            tier="paid",
            plan=sub.plan,
            expires_at=sub_expires,
            is_active=True,
        )

    # No active sub or expired — downgrade if needed
    if sub and sub_expires and sub_expires <= now and sub.status == "active":
        sub.status = "expired"
    if current_user.tier == "paid":
        current_user.tier = "free"
    await db.commit()

    return BillingStatusResponse(
        tier="free",
        plan=None,
        expires_at=None,
        is_active=False,
    )
