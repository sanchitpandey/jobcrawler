"""
Application model — replaces tracker.py's jobs table.
Adds user_id FK and an audit trail of what was submitted.

Status flow: scored → approved → applying → applied → interview → offer → rejected
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models.base import Base

if TYPE_CHECKING:
    from api.models.user import User


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Job identity (mirrors tracker.py JobRecord) ────────────────────────────
    external_id: Mapped[str | None] = mapped_column(String(64), index=True)  # make_id hash
    company: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(2000))
    description: Mapped[str | None] = mapped_column(Text)

    # ── Scoring results ────────────────────────────────────────────────────────
    fit_score: Mapped[float | None] = mapped_column(Float)
    comp_est: Mapped[str | None] = mapped_column(String(100))
    verdict: Mapped[str | None] = mapped_column(String(50))   # strong_yes / yes / maybe / no
    gaps: Mapped[list[str] | None] = mapped_column(JSON)      # list of gap strings

    # ── Status tracking ────────────────────────────────────────────────────────
    # scored → approved → applying → applied → interview → offer → rejected
    status: Mapped[str] = mapped_column(
        String(30), default="scored", nullable=False, index=True
    )

    # ── ATS metadata ──────────────────────────────────────────────────────────
    ats_type: Mapped[str | None] = mapped_column(String(50))      # linkedin / greenhouse / lever / indeed
    difficulty: Mapped[str | None] = mapped_column(String(20))    # easy / medium / hard

    # ── Submission audit trail ─────────────────────────────────────────────────
    filled_fields_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cover_letter: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── LLM metadata ──────────────────────────────────────────────────────────
    scored_model: Mapped[str | None] = mapped_column(String(100))
    llm_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ── Timestamps ─────────────────────────────────────────────────────────────
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship("User", back_populates="applications")

    def __repr__(self) -> str:
        return f"<Application id={self.id} company={self.company!r} status={self.status}>"
