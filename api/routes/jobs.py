"""
Job routes.

POST /score-job — score a single job listing against the authenticated user's profile.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.base import get_db
from api.models.profile import Profile
from api.models.user import User
from api.routes.auth import get_current_user
from api.services.scorer import score_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


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


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/score-job", response_model=ScoreJobResponse)
async def score_job_endpoint(
    req: ScoreJobRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScoreJobResponse:
    result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Please complete your profile before scoring jobs.",
        )

    try:
        scored = await score_job(
            job_dict=req.model_dump(),
            profile_text=profile.to_text(),
            profile_kv=profile.to_dict(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Scoring failed: {exc}",
        ) from exc

    return ScoreJobResponse(
        id=scored["id"],
        fit_score=int(scored.get("fit_score", 0)),
        comp_estimate=str(scored.get("comp_estimate", "")),
        verdict=str(scored.get("verdict", "skip")),
        gaps=list(scored.get("gaps", [])),
        why=str(scored.get("why", "")),
    )
