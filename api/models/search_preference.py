"""
SearchPreference model — one row per user, stores LinkedIn search config
and auto-apply thresholds.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base

if TYPE_CHECKING:
    from api.models.user import User


class SearchPreference(Base):
    __tablename__ = "search_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # ── LinkedIn search parameters ─────────────────────────────────────────────
    keywords: Mapped[list[str] | None] = mapped_column(JSON)                  # ["ml engineer", "data scientist"]
    location: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    experience_levels: Mapped[str] = mapped_column(String(20), default="", nullable=False)  # "2,3"
    remote_filter: Mapped[str] = mapped_column(String(10), default="", nullable=False)       # "" | "2" | "3"
    time_range: Mapped[str] = mapped_column(String(20), default="r86400", nullable=False)

    # ── Auto-apply settings ────────────────────────────────────────────────────
    auto_apply_threshold: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    max_daily_applications: Mapped[int] = mapped_column(Integer, default=15, nullable=False)

    # ── Blacklists (supplement Profile blacklists) ─────────────────────────────
    skip_companies: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    skip_title_keywords: Mapped[list[str] | None] = mapped_column(JSON, default=list)

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="search_preference")

    def __repr__(self) -> str:
        return f"<SearchPreference user_id={self.user_id!r} location={self.location!r}>"
