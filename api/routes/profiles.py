"""
Profile routes.

GET    /profile                 — return the current user's profile
POST   /profile                 — create profile (409 if already exists)
PATCH  /profile                 — partial update (upsert-safe)
POST   /profile/import-markdown — paste raw APPLY_PROFILE.md text → upsert
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.base import get_db
from api.models.profile import Profile
from api.models.user import User
from api.routes.auth import get_current_user

router = APIRouter(prefix="/profile", tags=["profile"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class ProfilePayload(BaseModel):
    """All fields optional — used for both POST (create) and PATCH (update)."""

    # Personal
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    location_current: str | None = None

    # Availability and compensation
    notice_period: str | None = None
    current_ctc: str | None = None
    expected_ctc: str | None = None
    expected_ctc_min_lpa: str | None = None
    start_date: str | None = None

    # Education
    degree: str | None = None
    college: str | None = None
    graduation_month_year: str | None = None
    graduation_year: str | None = None
    cgpa: str | None = None

    # Experience and authorization
    total_experience: str | None = None
    work_authorization: str | None = None
    willing_to_relocate: str | None = None
    willing_to_travel: str | None = None
    sponsorship_required: str | None = None

    # Technical skills  {"python_years": "3", "ml_years": "2", ...}
    skills: dict[str, str] | None = None

    # EEO  {"gender": "male", "ethnicity": "asian", ...}
    eeo: dict[str, str] | None = None

    # Job search preferences
    preferred_roles: str | None = Field(None, max_length=2000)
    target_locations: str | None = Field(None, max_length=1000)
    avoid_roles: str | None = Field(None, max_length=2000)
    avoid_companies: str | None = Field(None, max_length=2000)
    minimum_compensation: str | None = Field(None, max_length=500)
    must_have_preferences: str | None = Field(None, max_length=2000)
    deal_breakers: str | None = Field(None, max_length=2000)

    # Candidate summary
    candidate_summary: str | None = Field(None, max_length=5000)
    experience_highlights: str | None = Field(None, max_length=5000)

    # Short answers  {"why_ml_engineering": "...", ...}
    short_answers: dict[str, str] | None = None

    # Filtering / scoring preferences
    blacklist_companies: list[str] | None = None
    blacklist_keywords: list[str] | None = None
    min_comp_lpa: int | None = Field(None, ge=0, le=10_000_000)
    target_comp_lpa: int | None = Field(None, ge=0, le=10_000_000)


class ProfileResponse(BaseModel):
    id: str

    # Personal
    name: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None
    github_url: str | None
    portfolio_url: str | None
    location_current: str | None

    # Availability
    notice_period: str | None
    current_ctc: str | None
    expected_ctc: str | None
    expected_ctc_min_lpa: str | None
    start_date: str | None

    # Education
    degree: str | None
    college: str | None
    graduation_month_year: str | None
    graduation_year: str | None
    cgpa: str | None

    # Experience
    total_experience: str | None
    work_authorization: str | None
    willing_to_relocate: str | None
    willing_to_travel: str | None
    sponsorship_required: str | None

    # JSON blobs
    skills: dict[str, Any]
    eeo: dict[str, Any]
    short_answers: dict[str, Any]

    # Preferences
    preferred_roles: str | None
    target_locations: str | None
    avoid_roles: str | None
    avoid_companies: str | None
    minimum_compensation: str | None
    must_have_preferences: str | None
    deal_breakers: str | None

    # Summary
    candidate_summary: str | None
    experience_highlights: str | None

    # Filtering
    blacklist_companies: list[str]
    blacklist_keywords: list[str]
    min_comp_lpa: int
    target_comp_lpa: int

    model_config = {"from_attributes": True}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _profile_to_response(profile: Profile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        email=profile.email,
        phone=profile.phone,
        linkedin_url=profile.linkedin_url,
        github_url=profile.github_url,
        portfolio_url=profile.portfolio_url,
        location_current=profile.location_current,
        notice_period=profile.notice_period,
        current_ctc=profile.current_ctc,
        expected_ctc=profile.expected_ctc,
        expected_ctc_min_lpa=profile.expected_ctc_min_lpa,
        start_date=profile.start_date,
        degree=profile.degree,
        college=profile.college,
        graduation_month_year=profile.graduation_month_year,
        graduation_year=profile.graduation_year,
        cgpa=profile.cgpa,
        total_experience=profile.total_experience,
        work_authorization=profile.work_authorization,
        willing_to_relocate=profile.willing_to_relocate,
        willing_to_travel=profile.willing_to_travel,
        sponsorship_required=profile.sponsorship_required,
        skills=profile.skills_json or {},
        eeo=profile.eeo_json or {},
        short_answers=profile.short_answers_json or {},
        preferred_roles=profile.preferred_roles,
        target_locations=profile.target_locations,
        avoid_roles=profile.avoid_roles,
        avoid_companies=profile.avoid_companies,
        minimum_compensation=profile.minimum_compensation,
        must_have_preferences=profile.must_have_preferences,
        deal_breakers=profile.deal_breakers,
        candidate_summary=profile.candidate_summary,
        experience_highlights=profile.experience_highlights,
        blacklist_companies=profile.blacklist_companies or [],
        blacklist_keywords=profile.blacklist_keywords or [],
        min_comp_lpa=profile.min_comp_lpa,
        target_comp_lpa=profile.target_comp_lpa,
    )


def _apply_payload(profile: Profile, payload: ProfilePayload) -> None:
    """Write non-None payload fields onto a Profile instance in-place."""
    scalar_fields = [
        "name", "email", "phone", "linkedin_url", "github_url", "portfolio_url",
        "location_current", "notice_period", "current_ctc", "expected_ctc",
        "expected_ctc_min_lpa", "start_date", "degree", "college",
        "graduation_month_year", "graduation_year", "cgpa", "total_experience",
        "work_authorization", "willing_to_relocate", "willing_to_travel",
        "sponsorship_required", "preferred_roles", "target_locations", "avoid_roles",
        "avoid_companies", "minimum_compensation", "must_have_preferences",
        "deal_breakers", "candidate_summary", "experience_highlights",
        "blacklist_companies", "blacklist_keywords", "min_comp_lpa", "target_comp_lpa",
    ]
    for field in scalar_fields:
        value = getattr(payload, field)
        if value is not None:
            setattr(profile, field, value)

    if payload.skills is not None:
        profile.skills_json = {**(profile.skills_json or {}), **payload.skills}
    if payload.eeo is not None:
        profile.eeo_json = {**(profile.eeo_json or {}), **payload.eeo}
    if payload.short_answers is not None:
        profile.short_answers_json = {**(profile.short_answers_json or {}), **payload.short_answers}


# ── Markdown import ────────────────────────────────────────────────────────────

# Keys from APPLY_PROFILE.md that belong in skills_json
_SKILLS_KEYS = {
    "python_years", "ml_years", "llm_nlp_rag_years", "pytorch_years",
    "huggingface_years", "sql_years", "docker_years", "react_years",
}
# Keys that belong in eeo_json
_EEO_KEYS = {"gender", "ethnicity", "veteran_status", "disability"}

# Direct mapping: APPLY_PROFILE.md key → Profile column name
_SCALAR_KEY_MAP: dict[str, str] = {
    "name": "name",
    "email": "email",
    "phone": "phone",
    "linkedin": "linkedin_url",
    "github": "github_url",
    "portfolio": "portfolio_url",
    "location_current": "location_current",
    "notice_period": "notice_period",
    "current_ctc": "current_ctc",
    "expected_ctc": "expected_ctc",
    "expected_ctc_min_lpa": "expected_ctc_min_lpa",
    "start_date": "start_date",
    "degree": "degree",
    "college": "college",
    "graduation_month_year": "graduation_month_year",
    "graduation_year": "graduation_year",
    "cgpa": "cgpa",
    "total_experience": "total_experience",
    "work_authorization": "work_authorization",
    "willing_to_relocate": "willing_to_relocate",
    "willing_to_travel": "willing_to_travel",
    "sponsorship_required": "sponsorship_required",
    "preferred_roles": "preferred_roles",
    "target_locations": "target_locations",
    "avoid_roles": "avoid_roles",
    "avoid_companies": "avoid_companies",
    "minimum_compensation": "minimum_compensation",
    "must_have_preferences": "must_have_preferences",
    "deal_breakers": "deal_breakers",
    "candidate_summary": "candidate_summary",
    "experience_highlights": "experience_highlights",
}


def _parse_markdown_profile(text: str) -> dict[str, str]:
    """Parse APPLY_PROFILE.md format into a flat key-value dict.

    Ported from legacy/core/profile.py:load_key_value_profile — file I/O removed.
    """
    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            result[current_key] = "\n".join(line.rstrip() for line in current_lines).strip()
        current_key = None
        current_lines = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if current_key is not None and (line.startswith("  ") or line.startswith("\t")):
            current_lines.append(stripped)
            continue

        if ":" not in line:
            continue

        flush()
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value in {">", "|"}:
            current_key = key
            current_lines = []
            continue

        result[key] = value.strip('"')

    flush()
    return result


def _kv_to_profile(kv: dict[str, str], profile: Profile) -> None:
    """Apply a parsed key-value dict to a Profile instance in-place."""
    skills: dict[str, str] = {}
    eeo: dict[str, str] = {}
    short_answers: dict[str, str] = {}

    for key, value in kv.items():
        if key in _SCALAR_KEY_MAP:
            setattr(profile, _SCALAR_KEY_MAP[key], value)
        elif key in _SKILLS_KEYS:
            skills[key] = value
        elif key in _EEO_KEYS:
            eeo[key] = value
        else:
            # Anything else that isn't a section header goes into short_answers
            short_answers[key] = value

    if skills:
        profile.skills_json = {**(profile.skills_json or {}), **skills}
    if eeo:
        profile.eeo_json = {**(profile.eeo_json or {}), **eeo}
    if short_answers:
        profile.short_answers_json = {**(profile.short_answers_json or {}), **short_answers}


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return _profile_to_response(profile)


@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_profile(
    payload: ProfilePayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Profile already exists. Use PATCH /profile to update it.",
        )
    profile = Profile(user_id=current_user.id)
    _apply_payload(profile, payload)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return _profile_to_response(profile)


@router.patch("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfilePayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        # Auto-create on first PATCH so the extension doesn't need a two-step flow
        profile = Profile(user_id=current_user.id)
        db.add(profile)
    _apply_payload(profile, payload)
    await db.commit()
    await db.refresh(profile)
    return _profile_to_response(profile)


_MAX_MARKDOWN_BYTES = 100_000  # 100 KB


@router.post("/import-markdown", response_model=ProfileResponse)
async def import_markdown(
    markdown: str = Body(..., media_type="text/plain", max_length=_MAX_MARKDOWN_BYTES),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileResponse:
    """Paste the contents of APPLY_PROFILE.md to create or fully overwrite the profile."""
    kv = _parse_markdown_profile(markdown)
    if not kv:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not parse any fields from the provided markdown.",
        )

    result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = Profile(user_id=current_user.id)
        db.add(profile)

    _kv_to_profile(kv, profile)
    await db.commit()
    await db.refresh(profile)
    return _profile_to_response(profile)
