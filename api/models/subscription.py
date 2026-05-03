"""
Subscription model — tracks paid plan purchases via Razorpay.

Status flow: active → cancelled | expired
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Index, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base

if TYPE_CHECKING:
    from api.models.user import User


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_user_id_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "monthly" | "annual"
    plan: Mapped[str] = mapped_column(String(20), nullable=False)
    # "active" | "cancelled" | "expired"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    razorpay_order_id: Mapped[str | None] = mapped_column(String(100), index=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(100), index=True)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(String(100))

    # Amount in paise (49900 = ₹499)
    amount_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")

    def __repr__(self) -> str:
        return (
            f"<Subscription user={self.user_id} plan={self.plan}"
            f" status={self.status} expires={self.expires_at}>"
        )
