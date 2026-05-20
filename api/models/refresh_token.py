"""
Refresh token model — stores hashed refresh tokens with rotation + revocation.

Each successful /auth/refresh issues a new token (rotation) and marks the
previous row as `revoked`. Re-use of a revoked token revokes the entire family
(reuse detection), forcing re-login on the compromised device.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_user_id_revoked", "user_id", "revoked"),
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
    # jti claim — unique per token, also the lookup key
    jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # family_id ties together all tokens issued from a single login chain
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    # SHA-256 hash of the token string (defence in depth — never store plaintext)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # When the entire family was burned (reuse detected)
    family_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
