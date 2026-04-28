"""
Discovery routes — ingest raw jobs from extension, manage search preferences.

POST /discovery/ingest           — receive job cards, dedupe, filter, save
POST /discovery/enrich           — attach full description to a discovered job
POST /discovery/score-batch      — LLM-score all enriched jobs for the user
GET  /discovery/queue            — fetch approved jobs sorted by fit_score
PATCH /discovery/{app_id}/status — update application status
POST /discovery/approve-batch    — bulk-approve scored jobs above a score floor
GET  /discovery/preferences      — get user's SearchPreference
POST /discovery/preferences      — create or update SearchPreference
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.logger import get_logger
from api.models.application import Application
from api.models.base import get_db
from api.models.profile import Profile
from api.models.search_preference import SearchPreference
from api.routes.auth import get_current_user
from api.models.user import User
from api.services import scorer as scorer_svc
from api.services.filter import filter_job

router = APIRouter(prefix="/discovery", tags=["discovery"])
log = get_logger(__name__)


# ── Schemas ────────────────────────────────────────────────────────────────────

class RawJobIn(BaseModel):
    linkedin_job_id: str = Field(..., max_length=64)
    title: str = Field("", max_length=512)
    company: str = Field("", max_length=512)
    location: str = Field("", max_length=256)
    url: str = Field("", max_length=2000)
    posted_text: str = Field("", max_length=100)
    is_easy_apply: bool = True


class IngestRequest(BaseModel):
    jobs: list[RawJobIn]
    source: str = Field("linkedin_extension", max_length=50)


class IngestResponse(BaseModel):
    ingested: int
    filtered_count: int
    needs_enrichment: list[str]


class SearchPreferenceIn(BaseModel):
    keywords: list[str] | None = None
    location: str = ""
    experience_levels: str = ""
    remote_filter: str = ""
    time_range: str = "r86400"
    auto_apply_threshold: int = Field(75, ge=0, le=100)
    max_daily_applications: int = Field(15, ge=1, le=30)
    skip_companies: list[str] | None = None
    skip_title_keywords: list[str] | None = None


class SearchPreferenceOut(BaseModel):
    id: str
    keywords: list[str] | None
    location: str
    experience_levels: str
    remote_filter: str
    time_range: str
    auto_apply_threshold: int
    max_daily_applications: int
    skip_companies: list[str] | None
    skip_title_keywords: list[str] | None

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_profile_blacklists(
    user_id: str, db: AsyncSession
) -> tuple[list[str], list[str]]:
    """Return (blacklist_companies, blacklist_keywords) from user's Profile."""
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        return [], []
    return (profile.blacklist_companies or []), (profile.blacklist_keywords or [])


async def _get_search_preference(user_id: str, db: AsyncSession) -> SearchPreference | None:
    result = await db.execute(
        select(SearchPreference).where(SearchPreference.user_id == user_id)
    )
    return result.scalar_one_or_none()


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/ingest", response_model=IngestResponse)
async def ingest_jobs(
    body: IngestRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Receive raw job cards from extension.
    1. Dedupe against existing Applications (by external_id = "linkedin:{id}")
    2. Run filter.py blacklists on each
    3. Save survivors as Applications with status='discovered'
    4. Return list of linkedin_job_ids that need enrichment (full description)
    """
    if not body.jobs:
        return IngestResponse(ingested=0, filtered_count=0, needs_enrichment=[])

    # Build set of already-known external_ids for this user to detect duplicates fast
    all_ext_ids = [f"linkedin:{j.linkedin_job_id}" for j in body.jobs]
    existing_result = await db.execute(
        select(Application.external_id).where(
            Application.user_id == current_user.id,
            Application.external_id.in_(all_ext_ids),
        )
    )
    existing_ids: set[str] = {row[0] for row in existing_result.all()}

    blacklist_companies, blacklist_keywords = await _get_profile_blacklists(current_user.id, db)

    # Also pull skip lists from SearchPreference
    pref = await _get_search_preference(current_user.id, db)
    if pref:
        blacklist_companies = blacklist_companies + (pref.skip_companies or [])
        blacklist_keywords = blacklist_keywords + (pref.skip_title_keywords or [])

    batch_id = str(uuid.uuid4())
    ingested = 0
    filtered_count = 0
    needs_enrichment: list[str] = []

    for raw in body.jobs:
        ext_id = f"linkedin:{raw.linkedin_job_id}"

        # Skip duplicates
        if ext_id in existing_ids:
            filtered_count += 1
            continue

        job_dict: dict[str, Any] = {
            "title": raw.title,
            "company": raw.company,
            "location": raw.location,
            "description": "",
        }
        should_keep, reject_reason = filter_job(job_dict, blacklist_companies, blacklist_keywords)
        if not should_keep:
            log.debug("Filtered out %r: %s", raw.title, reject_reason)
            filtered_count += 1
            continue

        app = Application(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            external_id=ext_id,
            company=raw.company,
            title=raw.title,
            location=raw.location,
            url=raw.url,
            status="discovered",
            source=body.source,
            discovery_batch_id=batch_id,
            ats_type="linkedin",
        )
        db.add(app)
        existing_ids.add(ext_id)  # prevent same-batch dupes
        ingested += 1
        needs_enrichment.append(raw.linkedin_job_id)

    await db.commit()
    log.info(
        "Discovery ingest: ingested=%d filtered=%d batch=%s user=%s",
        ingested, filtered_count, batch_id, current_user.id,
    )
    return IngestResponse(
        ingested=ingested,
        filtered_count=filtered_count,
        needs_enrichment=needs_enrichment,
    )


@router.get("/preferences", response_model=SearchPreferenceOut)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchPreference:
    pref = await _get_search_preference(current_user.id, db)
    if pref is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No search preferences set")
    return pref


@router.post("/preferences", response_model=SearchPreferenceOut, status_code=status.HTTP_200_OK)
async def upsert_preferences(
    body: SearchPreferenceIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchPreference:
    """Create or replace the user's SearchPreference (upsert)."""
    pref = await _get_search_preference(current_user.id, db)
    if pref is None:
        pref = SearchPreference(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
        )
        db.add(pref)

    pref.keywords = body.keywords
    pref.location = body.location
    pref.experience_levels = body.experience_levels
    pref.remote_filter = body.remote_filter
    pref.time_range = body.time_range
    pref.auto_apply_threshold = body.auto_apply_threshold
    pref.max_daily_applications = body.max_daily_applications
    pref.skip_companies = body.skip_companies
    pref.skip_title_keywords = body.skip_title_keywords

    await db.commit()
    await db.refresh(pref)
    return pref


# ── Enrich ─────────────────────────────────────────────────────────────────────

class EnrichRequest(BaseModel):
    linkedin_job_id: str = Field(..., max_length=64)
    description: str = Field("", max_length=20000)
    applicant_count: str = Field("", max_length=100)


@router.post("/enrich")
async def enrich_job(
    body: EnrichRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    ext_id = f"linkedin:{body.linkedin_job_id}"
    result = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.external_id == ext_id,
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    app.description = body.description
    app.status = "enriched"
    await db.commit()
    return {"ok": True}


# ── Score-batch ────────────────────────────────────────────────────────────────

class ScoreBatchResponse(BaseModel):
    scored: int
    auto_approved: int
    needs_review: int


@router.post("/score-batch", response_model=ScoreBatchResponse)
async def score_batch(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreBatchResponse:
    """LLM-score all discovery Applications for the current user, sequentially."""
    # Prefer enriched rows, but do not let failed LinkedIn enrichment leave a
    # discovery batch permanently stuck at "Scored 0".
    apps_result = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.status.in_(("enriched", "discovered")),
            Application.source == "linkedin_extension",
        )
    )
    apps: list[Application] = list(apps_result.scalars().all())

    if not apps:
        return ScoreBatchResponse(scored=0, auto_approved=0, needs_review=0)

    # Load profile
    prof_result = await db.execute(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    profile = prof_result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User profile not found — create a profile before scoring",
        )

    profile_text = profile.to_text()
    profile_kv = profile.to_dict()

    # Load threshold from SearchPreference (default 75)
    pref = await _get_search_preference(current_user.id, db)
    threshold = pref.auto_apply_threshold if pref else 75

    scored_count = 0
    auto_approved = 0
    needs_review = 0

    for i, app in enumerate(apps):
        job_dict = {
            "id": app.id,
            "title": app.title or "",
            "company": app.company or "",
            "location": app.location or "",
            "description": app.description or "",
            "url": app.url or "",
        }
        try:
            result, tokens = await scorer_svc.score_job(job_dict, profile_text, profile_kv)
        except Exception as exc:
            log.warning("Scoring failed for app %s: %s", app.id, exc)
            app.status = "scored"
            app.fit_score = 0.0
            needs_review += 1
            continue

        app.fit_score = float(result.get("fit_score", 0))
        app.verdict = result.get("verdict")
        app.gaps = result.get("gaps")
        app.comp_est = result.get("comp_estimate")
        app.llm_tokens_used = tokens
        app.scored_at = datetime.now(tz=timezone.utc)

        if app.fit_score >= threshold:
            app.status = "approved"
            auto_approved += 1
        else:
            app.status = "scored"
            needs_review += 1

        scored_count += 1

        if (i + 1) % 10 == 0:
            log.info(
                "score-batch progress: %d/%d user=%s", i + 1, len(apps), current_user.id
            )

    await db.commit()
    log.info(
        "score-batch complete: scored=%d approved=%d review=%d user=%s",
        scored_count, auto_approved, needs_review, current_user.id,
    )
    return ScoreBatchResponse(
        scored=scored_count,
        auto_approved=auto_approved,
        needs_review=needs_review,
    )


# ── Queue ──────────────────────────────────────────────────────────────────────

class QueueItem(BaseModel):
    id: str
    url: str | None
    company: str | None
    title: str | None
    fit_score: float | None
    ats_type: str | None
    linkedin_job_id: str | None

    model_config = {"from_attributes": True}


class QueueResponse(BaseModel):
    queue: list[QueueItem]


@router.get("/queue", response_model=QueueResponse)
async def get_queue(
    status: str = "approved",
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueueResponse:
    result = await db.execute(
        select(Application)
        .where(
            Application.user_id == current_user.id,
            Application.status == status,
        )
        .order_by(Application.fit_score.desc().nulls_last())
        .limit(limit)
    )
    apps = result.scalars().all()

    queue = [
        QueueItem(
            id=app.id,
            url=app.url,
            company=app.company,
            title=app.title,
            fit_score=app.fit_score,
            ats_type=app.ats_type,
            linkedin_job_id=(
                app.external_id.removeprefix("linkedin:")
                if app.external_id and app.external_id.startswith("linkedin:")
                else None
            ),
        )
        for app in apps
    ]
    return QueueResponse(queue=queue)


# ── Status update ──────────────────────────────────────────────────────────────

_VALID_STATUSES = {
    "discovered", "enriched", "scored", "approved",
    "applying", "applied", "failed", "skipped", "rejected",
}

class StatusUpdateRequest(BaseModel):
    status: str
    filled_fields_json: dict[str, Any] | None = None


@router.patch("/{app_id}/status")
async def update_status(
    app_id: str,
    body: StatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{body.status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    result = await db.execute(
        select(Application).where(
            Application.id == app_id,
            Application.user_id == current_user.id,
        )
    )
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    app.status = body.status
    if body.filled_fields_json is not None:
        app.filled_fields_json = body.filled_fields_json
    if body.status == "applied":
        app.applied_at = datetime.now(tz=timezone.utc)

    await db.commit()
    return {"ok": True}


# ── Approve-batch ──────────────────────────────────────────────────────────────

class ApproveBatchRequest(BaseModel):
    min_score: int = Field(..., ge=0, le=100)


class ApproveBatchResponse(BaseModel):
    approved: int


@router.post("/approve-batch", response_model=ApproveBatchResponse)
async def approve_batch(
    body: ApproveBatchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApproveBatchResponse:
    result = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.status == "scored",
            Application.fit_score >= body.min_score,
        )
    )
    apps = result.scalars().all()

    for app in apps:
        app.status = "approved"

    await db.commit()
    log.info(
        "approve-batch: approved=%d min_score=%d user=%s",
        len(apps), body.min_score, current_user.id,
    )
    return ApproveBatchResponse(approved=len(apps))


# ── Stats ──────────────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    applied_today: int
    applied_week: int
    queue_approved: int
    scored_needs_review: int


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StatsResponse:
    now = datetime.now(tz=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)

    # Count by status in one query
    status_result = await db.execute(
        select(Application.status, func.count(Application.id))
        .where(Application.user_id == current_user.id)
        .group_by(Application.status)
    )
    status_counts: dict[str, int] = {row[0]: row[1] for row in status_result.all()}

    today_result = await db.execute(
        select(func.count(Application.id)).where(
            Application.user_id == current_user.id,
            Application.status == "applied",
            Application.applied_at >= today_start,
        )
    )
    applied_today: int = today_result.scalar_one() or 0

    week_result = await db.execute(
        select(func.count(Application.id)).where(
            Application.user_id == current_user.id,
            Application.status == "applied",
            Application.applied_at >= week_start,
        )
    )
    applied_week: int = week_result.scalar_one() or 0

    return StatsResponse(
        applied_today=applied_today,
        applied_week=applied_week,
        queue_approved=status_counts.get("approved", 0),
        scored_needs_review=status_counts.get("scored", 0),
    )
