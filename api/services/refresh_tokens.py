"""
Refresh-token lifecycle service.

Implements rotation + reuse detection:
- issue()    creates a new family for a fresh login.
- rotate()   validates the incoming token, marks it revoked, and issues a
             new one bound to the same family. If the incoming token is
             already revoked (= reuse), the entire family is burned.
- revoke()   marks a single token revoked (logout).
- revoke_family() burns every token tied to a family (forced sign-out).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.config import get_settings
from api.logger import get_logger
from api.models.refresh_token import RefreshToken

log = get_logger(__name__)
_settings = get_settings()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(
        days=_settings.jwt_refresh_token_expire_days
    )


async def issue(db: AsyncSession, user_id: str, family_id: str | None = None) -> tuple[str, str, str]:
    """
    Create and persist a new refresh token row.
    Returns (raw_token, jti, family_id).
    """
    jti = secrets.token_urlsafe(32)
    raw = secrets.token_urlsafe(48)
    family = family_id or str(uuid.uuid4())
    row = RefreshToken(
        user_id=user_id,
        jti=jti,
        family_id=family,
        token_hash=_hash(raw),
        expires_at=_expiry(),
    )
    db.add(row)
    await db.flush()
    # The raw token returned to the client is `<jti>.<secret>` so the server
    # can look up by jti without scanning the whole table.
    return f"{jti}.{raw}", jti, family


def parse(token: str) -> tuple[str, str] | None:
    """Split `<jti>.<secret>` into its parts; None if malformed."""
    if "." not in token:
        return None
    jti, _, secret = token.partition(".")
    if not jti or not secret:
        return None
    return jti, secret


async def rotate(db: AsyncSession, token: str) -> tuple[str, str] | None:
    """
    Validate + rotate a refresh token.

    Returns (new_raw_token, user_id) on success.
    Returns None when the token is invalid/expired/revoked. On replay of a
    previously revoked-but-known token, the entire family is burned.
    """
    parts = parse(token)
    if not parts:
        return None
    jti, secret = parts
    result = await db.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    row = result.scalar_one_or_none()
    if row is None:
        return None

    # Constant-time compare on the hash
    if not secrets.compare_digest(row.token_hash, _hash(secret)):
        return None

    now = datetime.now(timezone.utc)
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    if row.family_revoked or expires < now:
        return None

    if row.revoked:
        # Reuse detected — burn the entire family. Commit immediately so the
        # revocation survives even if the caller then raises an HTTPException
        # (which would normally trigger a rollback in the request scope).
        log.warning(
            "refresh-token reuse detected; revoking family",
            extra={"user_id": row.user_id, "family_id": row.family_id, "jti": jti},
        )
        await _revoke_family(db, row.family_id)
        await db.commit()
        return None

    row.revoked = True
    row.last_used_at = now
    await db.flush()

    new_raw, _, _ = await issue(db, row.user_id, family_id=row.family_id)
    return new_raw, row.user_id


async def revoke(db: AsyncSession, token: str) -> None:
    """Single-token revoke (logout). Silent on unknown tokens."""
    parts = parse(token)
    if not parts:
        return
    jti, _ = parts
    await db.execute(
        update(RefreshToken).where(RefreshToken.jti == jti).values(revoked=True)
    )


async def _revoke_family(db: AsyncSession, family_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id)
        .values(revoked=True, family_revoked=True)
    )


async def revoke_all_for_user(db: AsyncSession, user_id: str) -> None:
    """Force-logout the user from every device."""
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id)
        .values(revoked=True, family_revoked=True)
    )
