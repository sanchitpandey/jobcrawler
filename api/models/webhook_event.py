"""
Processed-webhook event log — audit fix #19.

Persists each Razorpay event ID after it has been handled. The webhook handler
consults this table to short-circuit replays (Razorpay retries on non-2xx and
event IDs can be replayed by an attacker who captures one).
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    # Razorpay event id (e.g. "evt_xxx") is globally unique per Razorpay account
    event_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
