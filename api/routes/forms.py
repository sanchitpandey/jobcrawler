"""
Form-fill routes.

POST /forms/answer-fields — given a list of form fields, return AI-generated answers
                            for the authenticated user's profile.
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
from api.services.cover_letter import generate_cover
from api.services.form_filler import FilledAnswer, answer_question_for_user

router = APIRouter(prefix="/forms", tags=["forms"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class FieldRequest(BaseModel):
    label: str
    field_type: str = "text"
    options: list[str] | None = None


class AnswerFieldsRequest(BaseModel):
    fields: list[FieldRequest]
    company: str = ""
    job_title: str = ""


class AnswerItem(BaseModel):
    label: str
    value: str
    source: str
    confidence: float
    is_manual_review: bool


class AnswerFieldsResponse(BaseModel):
    answers: list[AnswerItem]


class GenerateCoverRequest(BaseModel):
    company: str
    title: str
    location: str = ""
    description: str = ""


class GenerateCoverResponse(BaseModel):
    cover_letter: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/answer-fields", response_model=AnswerFieldsResponse)
async def answer_fields(
    req: AnswerFieldsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AnswerFieldsResponse:
    result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Please complete your profile before using form fill.",
        )

    candidate = profile.to_dict()
    profile_text = profile.to_text()

    answers: list[AnswerItem] = []
    for field in req.fields:
        filled: FilledAnswer = await answer_question_for_user(
            question_text=field.label,
            field_type=field.field_type,
            options=field.options,
            company=req.company,
            job_title=req.job_title,
            candidate=candidate,
            profile_text=profile_text,
            user_id=current_user.id,
        )
        answers.append(
            AnswerItem(
                label=field.label,
                value=filled.value,
                source=filled.source,
                confidence=filled.confidence,
                is_manual_review=filled.is_manual_review,
            )
        )

    return AnswerFieldsResponse(answers=answers)


@router.post("/generate-cover", response_model=GenerateCoverResponse)
async def generate_cover_letter(
    req: GenerateCoverRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerateCoverResponse:
    result = await db.execute(select(Profile).where(Profile.user_id == current_user.id))
    profile = result.scalar_one_or_none()

    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found. Please complete your profile before generating cover letters.",
        )

    try:
        letter = await generate_cover(
            job_dict=req.model_dump(),
            profile_text=profile.to_text(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cover letter generation failed: {exc}",
        ) from exc

    return GenerateCoverResponse(cover_letter=letter)
