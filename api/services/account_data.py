"""
Account data export + erasure service — implements user rights under GDPR
Art. 15/17 and India's DPDP Act §11/§12.

The route layer stays thin (auth check, password reverification, rate limit);
this module owns the data shape and the cascade.

Cascade ownership
-----------------
The User row has FK ``ondelete=CASCADE`` to: Profile, Application, Subscription,
SearchPreference, RefreshToken. Deleting the user therefore drops every related
row in one statement.

``LlmUsageLog.user_id`` is a plain ``String`` without a ForeignKey (the table
was originally append-only telemetry), so we delete those rows explicitly
before dropping the user. A future migration should add the FK + CASCADE for
defence in depth — see the TODO in ``llm_usage.py``.

Resume files live on disk under ``api/uploads`` and are not under the DB
cascade — we unlink them explicitly.

Legal-retention note
--------------------
We currently hard-delete Subscription rows. Razorpay retains the canonical
payment/invoice records on their side, so the tax-retention obligation
(India GST: 7 years) is satisfied by the payment processor's books. If you
later need an in-app invoice archive, switch ``Subscription.user_id`` to
nullable and anonymise (set user_id=NULL, retain amount/dates) instead of
deleting — but until then, hard-delete is the simpler GDPR-compliant choice.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.logger import get_logger
from api.models.application import Application
from api.models.llm_usage import LlmUsageLog
from api.models.profile import Profile
from api.models.refresh_token import RefreshToken
from api.models.search_preference import SearchPreference
from api.models.subscription import Subscription
from api.models.user import User

log = get_logger(__name__)


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


async def export_user_data(user: User, db: AsyncSession) -> dict[str, Any]:
    """Build a portable JSON archive of every row the user owns.

    Sensitive material that is NOT user-owned (password hash, bcrypt'd
    verification codes, refresh-token hashes) is omitted. Refresh-token
    metadata (jti / family / timestamps / revoked flags) is included so a
    user can audit their own session history.
    """
    profile_row = (
        await db.execute(select(Profile).where(Profile.user_id == user.id))
    ).scalar_one_or_none()

    applications = (
        await db.execute(select(Application).where(Application.user_id == user.id))
    ).scalars().all()

    subscriptions = (
        await db.execute(select(Subscription).where(Subscription.user_id == user.id))
    ).scalars().all()

    search_pref = (
        await db.execute(
            select(SearchPreference).where(SearchPreference.user_id == user.id)
        )
    ).scalar_one_or_none()

    usage_rows = (
        await db.execute(select(LlmUsageLog).where(LlmUsageLog.user_id == user.id))
    ).scalars().all()

    refresh_rows = (
        await db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id))
    ).scalars().all()

    archive: dict[str, Any] = {
        "export_format_version": 1,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "account": {
            "id": user.id,
            "email": user.email,
            "tier": user.tier,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
        },
        "profile": profile_row.to_dict() if profile_row else None,
        "applications": [
            {
                "id": a.id,
                "external_id": a.external_id,
                "company": a.company,
                "title": a.title,
                "location": a.location,
                "url": a.url,
                "description": a.description,
                "fit_score": a.fit_score,
                "comp_est": a.comp_est,
                "verdict": a.verdict,
                "gaps": a.gaps,
                "status": a.status,
                "source": a.source,
                "ats_type": a.ats_type,
                "difficulty": a.difficulty,
                "filled_fields": a.filled_fields_json,
                "cover_letter": a.cover_letter,
                "applied_at": _iso(a.applied_at),
                "scored_model": a.scored_model,
                "llm_tokens_used": a.llm_tokens_used,
                "scored_at": _iso(a.scored_at),
                "updated_at": _iso(a.updated_at),
            }
            for a in applications
        ],
        "subscriptions": [
            {
                "id": s.id,
                "plan": s.plan,
                "status": s.status,
                "amount_paise": s.amount_paise,
                "currency": s.currency,
                "razorpay_order_id": s.razorpay_order_id,
                "razorpay_payment_id": s.razorpay_payment_id,
                "razorpay_subscription_id": s.razorpay_subscription_id,
                "starts_at": _iso(s.starts_at),
                "expires_at": _iso(s.expires_at),
                "created_at": _iso(s.created_at),
            }
            for s in subscriptions
        ],
        "search_preference": (
            {
                "keywords": search_pref.keywords,
                "location": search_pref.location,
                "experience_levels": search_pref.experience_levels,
                "remote_filter": search_pref.remote_filter,
                "time_range": search_pref.time_range,
                "auto_apply_threshold": search_pref.auto_apply_threshold,
                "max_daily_applications": search_pref.max_daily_applications,
                "skip_companies": search_pref.skip_companies,
                "skip_title_keywords": search_pref.skip_title_keywords,
                "created_at": _iso(search_pref.created_at),
                "updated_at": _iso(search_pref.updated_at),
            }
            if search_pref
            else None
        ),
        "llm_usage": [
            {
                "id": u.id,
                "tokens": u.tokens,
                "model": u.model,
                "call_type": u.call_type,
                "created_at": _iso(u.created_at),
            }
            for u in usage_rows
        ],
        "sessions": [
            {
                "jti": r.jti,
                "family_id": r.family_id,
                "revoked": r.revoked,
                "family_revoked": r.family_revoked,
                "created_at": _iso(r.created_at),
                "last_used_at": _iso(r.last_used_at),
                "expires_at": _iso(r.expires_at),
            }
            for r in refresh_rows
        ],
    }
    return archive


async def delete_user_and_data(
    user: User, db: AsyncSession, upload_dir: Path
) -> None:
    """Hard-delete the user and every row of personal data they own.

    The ORM-level FK CASCADE handles cleanup in Postgres, but SQLite
    (the dev/test DB) has ``PRAGMA foreign_keys=OFF`` by default and would
    otherwise leave orphans. To stay deterministic across both backends —
    and to make the intent explicit for future readers — we issue one
    DELETE per table rather than relying on the cascade. Order doesn't
    matter because the parent ``users`` row is the last to go.

    Steps:
      1. Resolve the resume file path before any rows are dropped.
      2. DELETE from every table that references the user.
      3. DELETE the User row.
      4. Commit once — all deletes are atomic.
      5. Best-effort unlink the resume file. Failure is logged but does not
         roll back: the DB row is authoritative for "deleted", and a stale
         PDF on disk is a janitor problem, not a compliance one.
    """
    profile_row = (
        await db.execute(select(Profile).where(Profile.user_id == user.id))
    ).scalar_one_or_none()
    resume_path = profile_row.resume_path if profile_row else None

    user_id = user.id
    await db.execute(delete(LlmUsageLog).where(LlmUsageLog.user_id == user_id))
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.execute(delete(Application).where(Application.user_id == user_id))
    await db.execute(delete(Subscription).where(Subscription.user_id == user_id))
    await db.execute(
        delete(SearchPreference).where(SearchPreference.user_id == user_id)
    )
    await db.execute(delete(Profile).where(Profile.user_id == user_id))
    await db.delete(user)
    await db.commit()

    if resume_path:
        _safe_unlink_resume(resume_path, upload_dir)


def _safe_unlink_resume(path_str: str, upload_dir: Path) -> None:
    """Unlink the resume file only if it resolves inside ``upload_dir``.

    Mirrors the path-traversal guard from the resume download route (audit
    fix #15): a manipulated DB row pointing outside the upload directory
    must not let account-deletion remove arbitrary files.
    """
    try:
        candidate = Path(path_str).resolve()
        candidate.relative_to(upload_dir.resolve())
    except (OSError, ValueError):
        log.warning(
            "skip resume unlink: path outside upload dir",
            extra={"path": path_str},
        )
        return
    try:
        candidate.unlink(missing_ok=True)
    except OSError as exc:
        log.warning("resume unlink failed", extra={"path": str(candidate), "error": str(exc)})
