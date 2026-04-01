"""
Job / application tracking routes.

POST   /jobs                     — track a new job (create Application record)
GET    /jobs                     — list applications (filterable)
GET    /jobs/{app_id}            — single application detail
PATCH  /jobs/{app_id}/status     — advance status, optionally attach filled fields / cover letter
POST   /jobs/score-job           — score a job against the user's profile (no DB write)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.middleware.rate_limit import check_apply_limit, get_usage
from api.middleware.usage import record_usage
from api.services.llm import current_model
from api.models.application import Application
from api.models.base import get_db
from api.models.profile import Profile
from api.models.user import User
from api.routes.auth import get_current_user
from api.services.filter import make_id
from api.services.scorer import score_job

router = APIRouter(prefix="/jobs", tags=["jobs"])

_VALID_STATUSES = frozenset({
    "scored", "approved", "applying", "applied",
    "interview", "offer", "rejected", "manual_review", "skipped", "error",
})


# ── Schemas ────────────────────────────────────────────────────────────────────

class ScoreJobRequest(BaseModel):
    id: str
    title: str
    company: str
    location: str = ""
    description: str = ""
    is_remote: bool = False


class ScoreJobResponse(BaseModel):
    id: str
    fit_score: int
    comp_estimate: str
    verdict: str
    gaps: list[str]
    why: str


class TrackJobRequest(BaseModel):
    """Persist a job (with optional score) into the application tracker."""
    company: str
    title: str
    location: str = ""
    url: str = ""
    description: str = ""
    is_remote: bool = False

    # ATS metadata (from ats_router, resolved by extension)
    ats_type: str | None = None
    difficulty: str | None = None

    # Scoring results — pass these in if /score-job was already called
    fit_score: int | None = None
    comp_est: str | None = None
    verdict: str | None = None
    gaps: list[str] | None = None

    # Optionally set an explicit external ID (make_id hash); computed if omitted
    external_id: str | None = None


class ApplicationResponse(BaseModel):
    id: str
    external_id: str | None
    company: str | None
    title: str | None
    location: str | None
    url: str | None
    fit_score: float | None
    comp_est: str | None
    verdict: str | None
    gaps: list[str] | None
    status: str
    ats_type: str | None
    difficulty: str | None
    cover_letter: str | None
    filled_fields_json: dict[str, Any] | None
    applied_at: datetime | None
    scored_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ApplicationListResponse(BaseModel):
    total: int
    items: list[ApplicationResponse]


class StatusUpdateRequest(BaseModel):
    status: str
    # Extension attaches these when submitting the application
    filled_fields_json: dict[str, Any] | None = None
    cover_letter: str | None = None


class UsageResponse(BaseModel):
    used: int
    limit: int        # -1 means unlimited (paid tier)
    resets_at: datetime
    is_paid: bool


# ── Helpers ────────────────────────────────────────────────────────────────────

def _app_to_response(app: Application) -> ApplicationResponse:
    return ApplicationResponse(
        id=app.id,
        external_id=app.external_id,
        company=app.company,
        title=app.title,
        location=app.location,
        url=app.url,
        fit_score=app.fit_score,
        comp_est=app.comp_est,
        verdict=app.verdict,
        gaps=app.gaps,
        status=app.status,
        ats_type=app.ats_type,
        difficulty=app.difficulty,
        cover_letter=app.cover_letter,
        filled_fields_json=app.filled_fields_json,
        applied_at=app.applied_at,
        scored_at=app.scored_at,
        updated_at=app.updated_at,
    )


async def _require_profile(user_id: str, db: AsyncSession) -> Profile:
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Please complete your profile first.",
        )
    return profile


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/score-job", response_model=ScoreJobResponse)
async def score_job_endpoint(
    req: ScoreJobRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreJobResponse:
    """Score a job against the user's profile. Does not persist to the tracker."""
    profile = await _require_profile(current_user.id, db)

    try:
        scored, tokens = await score_job(
            job_dict=req.model_dump(),
            profile_text=profile.to_text(),
            profile_kv=profile.to_dict(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Scoring failed: {exc}") from exc

    await record_usage(
        user_id=current_user.id,
        tokens=tokens,
        model=current_model(),
        call_type="score",
        db=db,
    )

    return ScoreJobResponse(
        id=scored["id"],
        fit_score=int(scored.get("fit_score", 0)),
        comp_estimate=str(scored.get("comp_estimate", "")),
        verdict=str(scored.get("verdict", "skip")),
        gaps=list(scored.get("gaps", [])),
        why=str(scored.get("why", "")),
    )


@router.get("/usage", response_model=UsageResponse)
async def get_apply_usage(
    usage=Depends(get_usage),
) -> UsageResponse:
    """Return the current user's weekly application usage.

    ``limit == -1`` means unlimited (paid tier).
    """
    return UsageResponse(
        used=usage.used,
        limit=usage.limit,
        resets_at=usage.resets_at,
        is_paid=usage.is_paid,
    )


@router.post("", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(check_apply_limit)])
async def track_job(
    req: TrackJobRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    """Add a job to the application tracker.

    The extension calls this (with or without scoring data) to persist a job.
    If the same external_id already exists for this user, returns the existing
    record instead of creating a duplicate (idempotent).
    """
    ext_id = req.external_id or make_id(req.company, req.title, req.location)

    # Idempotency — return existing record if already tracked
    existing = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.external_id == ext_id,
        )
    )
    app = existing.scalar_one_or_none()
    if app is not None:
        return _app_to_response(app)

    app = Application(
        user_id=current_user.id,
        external_id=ext_id,
        company=req.company,
        title=req.title,
        location=req.location,
        url=req.url,
        description=req.description,
        ats_type=req.ats_type,
        difficulty=req.difficulty,
        fit_score=req.fit_score,
        comp_est=req.comp_est,
        verdict=req.verdict,
        gaps=req.gaps,
        status="scored" if req.fit_score is not None else "new",
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)


@router.get("", response_model=ApplicationListResponse)
async def list_jobs(
    status_filter: str | None = Query(None, alias="status"),
    verdict: str | None = Query(None),
    min_score: int | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationListResponse:
    """List the current user's tracked applications."""
    base = select(Application).where(Application.user_id == current_user.id)

    if status_filter:
        base = base.where(Application.status == status_filter)
    if verdict:
        base = base.where(Application.verdict == verdict)
    if min_score is not None:
        base = base.where(Application.fit_score >= min_score)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    rows = await db.execute(
        base.order_by(Application.scored_at.desc()).limit(limit).offset(offset)
    )
    items = [_app_to_response(app) for app in rows.scalars().all()]
    return ApplicationListResponse(total=total, items=items)


@router.get("/{app_id}", response_model=ApplicationResponse)
async def get_job(
    app_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    result = await db.execute(
        select(Application).where(
            Application.id == app_id,
            Application.user_id == current_user.id,
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")
    return _app_to_response(app)


@router.patch("/{app_id}/status", response_model=ApplicationResponse)
async def update_status(
    app_id: str,
    req: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApplicationResponse:
    """Advance the status of an application.

    When status becomes 'applied', applied_at is stamped automatically.
    The extension also uses this to attach filled_fields_json and cover_letter
    after submitting.
    """
    if req.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status {req.status!r}. Valid values: {sorted(_VALID_STATUSES)}",
        )

    result = await db.execute(
        select(Application).where(
            Application.id == app_id,
            Application.user_id == current_user.id,
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found.")

    app.status = req.status

    if req.status == "applied" and app.applied_at is None:
        app.applied_at = datetime.now(timezone.utc)

    if req.filled_fields_json is not None:
        app.filled_fields_json = req.filled_fields_json
    if req.cover_letter is not None:
        app.cover_letter = req.cover_letter

    await db.commit()
    await db.refresh(app)
    return _app_to_response(app)
