"""Integration tests for form-fill and cover-letter endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from api.services.form_filler import FilledAnswer

pytestmark = pytest.mark.asyncio


def _make_filled(value: str, source: str = "pattern", confidence: float = 1.0,
                 is_manual: bool = False) -> FilledAnswer:
    return FilledAnswer(
        value=value,
        source=source,
        confidence=confidence,
        is_manual_review=is_manual,
    )


# ── POST /forms/answer-fields ─────────────────────────────────────────────────

async def test_answer_fields_requires_profile(
    test_client: AsyncClient, auth_headers: dict
):
    """Returns 404 when the user has no profile."""
    resp = await test_client.post(
        "/forms/answer-fields",
        json={
            "fields": [{"label": "Email", "field_type": "email"}],
            "company": "Acme",
            "job_title": "ML Engineer",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_answer_fields_pattern(
    test_client: AsyncClient, user_with_profile: dict
):
    """A simple email field is matched by pattern (no LLM call)."""
    mock_answer = _make_filled("test@example.com", source="pattern", confidence=1.0)

    with patch(
        "api.routes.forms.answer_question_for_user",
        new_callable=AsyncMock,
        return_value=(mock_answer, 0),
    ):
        resp = await test_client.post(
            "/forms/answer-fields",
            json={
                "fields": [{"label": "Email address", "field_type": "email"}],
                "company": "Acme",
                "job_title": "ML Engineer",
            },
            headers=user_with_profile["headers"],
        )

    assert resp.status_code == 200
    answers = resp.json()["answers"]
    assert len(answers) == 1
    assert answers[0]["value"] == "test@example.com"
    assert answers[0]["source"] == "pattern"
    assert answers[0]["is_manual_review"] is False


async def test_answer_fields_manual_review(
    test_client: AsyncClient, user_with_profile: dict
):
    """Open-ended questions are flagged for manual review."""
    mock_answer = _make_filled(
        "Please review this answer.", source="llm", confidence=0.7, is_manual=True
    )

    with patch(
        "api.routes.forms.answer_question_for_user",
        new_callable=AsyncMock,
        return_value=(mock_answer, 50),
    ):
        resp = await test_client.post(
            "/forms/answer-fields",
            json={
                "fields": [
                    {
                        "label": "Describe a time you faced a challenge at work",
                        "field_type": "textarea",
                    }
                ],
                "company": "Acme",
                "job_title": "ML Engineer",
            },
            headers=user_with_profile["headers"],
        )

    assert resp.status_code == 200
    answers = resp.json()["answers"]
    assert answers[0]["is_manual_review"] is True
    assert answers[0]["source"] == "llm"


async def test_answer_fields_multiple(
    test_client: AsyncClient, user_with_profile: dict
):
    """Multiple fields are answered and returned in order."""
    mock_answers = [
        (_make_filled("test@example.com"), 0),
        (_make_filled("Sanchit Pandey"), 0),
    ]

    with patch(
        "api.routes.forms.answer_question_for_user",
        new_callable=AsyncMock,
        side_effect=mock_answers,
    ):
        resp = await test_client.post(
            "/forms/answer-fields",
            json={
                "fields": [
                    {"label": "Email", "field_type": "email"},
                    {"label": "Full name", "field_type": "text"},
                ],
                "company": "Acme",
                "job_title": "ML Engineer",
            },
            headers=user_with_profile["headers"],
        )

    assert resp.status_code == 200
    answers = resp.json()["answers"]
    assert len(answers) == 2
    assert answers[0]["label"] == "Email"
    assert answers[1]["label"] == "Full name"


# ── POST /forms/generate-cover ────────────────────────────────────────────────

async def test_generate_cover_requires_profile(
    test_client: AsyncClient, auth_headers: dict
):
    resp = await test_client.post(
        "/forms/generate-cover",
        json={
            "company": "Acme",
            "title": "ML Engineer",
            "description": "Build LLMs.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404


async def test_generate_cover(test_client: AsyncClient, user_with_profile: dict):
    mock_letter = "Dear Hiring Manager,\n\nI am excited to apply..."

    with patch(
        "api.routes.forms.generate_cover",
        new_callable=AsyncMock,
        return_value=(mock_letter, 200),
    ):
        resp = await test_client.post(
            "/forms/generate-cover",
            json={
                "company": "Acme AI",
                "title": "ML Engineer",
                "description": "Build production ML pipelines.",
            },
            headers=user_with_profile["headers"],
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "cover_letter" in body
    assert "Dear Hiring Manager" in body["cover_letter"]
