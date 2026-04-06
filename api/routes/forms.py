"""
Form-fill routes.

POST /forms/answer-fields — given a list of form fields, return AI-generated answers
                            for the authenticated user's profile.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.logger import get_logger
from api.middleware.rate_limit import check_llm_limit
from api.middleware.usage import record_usage
from api.models.base import get_db
from api.models.profile import Profile
from api.models.user import User
from api.routes.auth import get_current_user
from api.services.cover_letter import generate_cover
from api.services.form_filler import FilledAnswer, answer_question_for_user
from api.services.llm import current_model

router = APIRouter(prefix="/forms", tags=["forms"])
log = get_logger(__name__)


# ── Schemas ────────────────────────────────────────────────────────────────────

class FieldRequest(BaseModel):
    label: str = Field(..., max_length=512)
    field_type: str = Field("text", max_length=50)
    options: list[str] | None = None
    validation_error: str = Field("", max_length=512)


class AnswerFieldsRequest(BaseModel):
    fields: list[FieldRequest] = Field(..., max_length=100)
    company: str = Field("", max_length=512)
    job_title: str = Field("", max_length=512)


class AnswerItem(BaseModel):
    label: str
    value: str
    source: str
    confidence: float
    is_manual_review: bool


class AnswerFieldsResponse(BaseModel):
    answers: list[AnswerItem]


class GenerateCoverRequest(BaseModel):
    company: str = Field(..., max_length=512)
    title: str = Field(..., max_length=512)
    location: str = Field("", max_length=256)
    description: str = Field("", max_length=50_000)


class GenerateCoverResponse(BaseModel):
    cover_letter: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/answer-fields", response_model=AnswerFieldsResponse,
             dependencies=[Depends(check_llm_limit)])
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
    total_tokens = 0
    for field in req.fields:
        filled, tokens = await answer_question_for_user(
            question_text=field.label,
            field_type=field.field_type,
            options=field.options,
            company=req.company,
            job_title=req.job_title,
            candidate=candidate,
            profile_text=profile_text,
            validation_error=field.validation_error,
            user_id=current_user.id,
        )
        total_tokens += tokens
        answers.append(
            AnswerItem(
                label=field.label,
                value=filled.value,
                source=filled.source,
                confidence=filled.confidence,
                is_manual_review=filled.is_manual_review,
            )
        )

    if total_tokens > 0:
        await record_usage(
            user_id=current_user.id,
            tokens=total_tokens,
            model=current_model(),
            call_type="form_fill",
            db=db,
        )

    return AnswerFieldsResponse(answers=answers)


@router.post("/generate-cover", response_model=GenerateCoverResponse,
             dependencies=[Depends(check_llm_limit)])
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
        letter, tokens = await generate_cover(
            job_dict=req.model_dump(),
            profile_text=profile.to_text(),
        )
    except Exception as exc:
        log.error("Cover letter generation failed for user %s: %s", current_user.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Cover letter generation temporarily unavailable. Please try again.",
        ) from exc

    await record_usage(
        user_id=current_user.id,
        tokens=tokens,
        model=current_model(),
        call_type="cover_letter",
        db=db,
    )

    return GenerateCoverResponse(cover_letter=letter)
