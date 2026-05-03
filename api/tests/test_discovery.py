"""Integration tests for api/routes/discovery.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from api.main import app
from api.models.application import Application
from api.models.base import get_db
from api.models.user import User

pytestmark = pytest.mark.asyncio


@asynccontextmanager
async def _db_session():
    override = app.dependency_overrides[get_db]
    agen = override()
    session = await agen.__anext__()
    try:
        yield session
    finally:
        try:
            await agen.__anext__()
        except StopAsyncIteration:
            pass


async def _get_user_id(email: str) -> str:
    async with _db_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        return user.id


async def _get_app_by_external_id(user_id: str, external_id: str) -> Application:
    async with _db_session() as session:
        result = await session.execute(
            select(Application).where(
                Application.user_id == user_id,
                Application.external_id == external_id,
            )
        )
        return result.scalar_one()


async def _create_application(user_id: str, **kwargs) -> Application:
    app_row = Application(
        user_id=user_id,
        company=kwargs.get("company", "Acme AI"),
        title=kwargs.get("title", "ML Engineer"),
        location=kwargs.get("location", "Remote"),
        url=kwargs.get("url", "https://example.com/job"),
        external_id=kwargs.get("external_id"),
        description=kwargs.get("description"),
        status=kwargs.get("status", "discovered"),
        source=kwargs.get("source", "linkedin_extension"),
        discovery_batch_id=kwargs.get("discovery_batch_id"),
        ats_type=kwargs.get("ats_type", "linkedin"),
        fit_score=kwargs.get("fit_score"),
        verdict=kwargs.get("verdict"),
        gaps=kwargs.get("gaps"),
        comp_est=kwargs.get("comp_est"),
        llm_tokens_used=kwargs.get("llm_tokens_used", 0),
        filled_fields_json=kwargs.get("filled_fields_json"),
        applied_at=kwargs.get("applied_at"),
        scored_at=kwargs.get("scored_at", datetime.now(timezone.utc)),
    )
    async with _db_session() as session:
        session.add(app_row)
        await session.flush()
        await session.refresh(app_row)
        return app_row


async def test_ingest_jobs_dedupes_and_filters(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    email = user_with_profile["user"]["email"]

    patch_resp = await test_client.patch(
        "/profile",
        json={
            "blacklist_companies": ["Blocked Co"],
            "blacklist_keywords": ["intern"],
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200

    pref_resp = await test_client.post(
        "/discovery/preferences",
        json={
            "skip_companies": ["Skip Corp"],
            "skip_title_keywords": ["staff"],
        },
        headers=headers,
    )
    assert pref_resp.status_code == 200

    payload = {
        "jobs": [
            {
                "linkedin_job_id": "100",
                "title": "ML Engineer",
                "company": "Good AI",
                "location": "Remote",
                "url": "https://example.com/jobs/100",
            },
            {
                "linkedin_job_id": "100",
                "title": "ML Engineer",
                "company": "Good AI",
                "location": "Remote",
                "url": "https://example.com/jobs/100-dup",
            },
            {
                "linkedin_job_id": "101",
                "title": "Data Scientist",
                "company": "Blocked Co",
                "location": "Remote",
                "url": "https://example.com/jobs/101",
            },
            {
                "linkedin_job_id": "102",
                "title": "Staff ML Engineer",
                "company": "Nice Startup",
                "location": "Remote",
                "url": "https://example.com/jobs/102",
            },
            {
                "linkedin_job_id": "103",
                "title": "Platform Engineer",
                "company": "Skip Corp",
                "location": "Remote",
                "url": "https://example.com/jobs/103",
            },
        ]
    }

    resp = await test_client.post("/discovery/ingest", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "ingested": 1,
        "filtered_count": 4,
        "needs_enrichment": ["100"],
    }

    user_id = await _get_user_id(email)
    app_row = await _get_app_by_external_id(user_id, "linkedin:100")
    assert app_row.title == "ML Engineer"
    assert app_row.status == "discovered"
    assert app_row.source == "linkedin_extension"

    second_resp = await test_client.post(
        "/discovery/ingest",
        json={"jobs": [payload["jobs"][0]]},
        headers=headers,
    )
    assert second_resp.status_code == 200
    assert second_resp.json() == {
        "ingested": 0,
        "filtered_count": 1,
        "needs_enrichment": [],
    }


async def test_enrich_updates_description_and_status(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    user_id = await _get_user_id(user_with_profile["user"]["email"])
    await _create_application(
        user_id,
        external_id="linkedin:enrich-1",
        status="discovered",
        description="",
    )

    resp = await test_client.post(
        "/discovery/enrich",
        json={
            "linkedin_job_id": "enrich-1",
            "description": "Build LLM pipelines and ship evaluation systems.",
            "applicant_count": "23 applicants",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    app_row = await _get_app_by_external_id(user_id, "linkedin:enrich-1")
    assert app_row.description == "Build LLM pipelines and ship evaluation systems."
    assert app_row.status == "enriched"


async def test_score_batch_scores_jobs_and_auto_approves_above_threshold(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    user_id = await _get_user_id(user_with_profile["user"]["email"])

    pref_resp = await test_client.post(
        "/discovery/preferences",
        json={"auto_apply_threshold": 80},
        headers=headers,
    )
    assert pref_resp.status_code == 200

    app_one = await _create_application(
        user_id,
        external_id="linkedin:score-1",
        title="ML Engineer",
        company="Good AI",
        status="enriched",
        description="Production ML systems and LLM tooling.",
    )
    app_two = await _create_application(
        user_id,
        external_id="linkedin:score-2",
        title="Data Scientist",
        company="Analytics Co",
        status="enriched",
        description="Dashboards with light ML support.",
    )

    scores = [
        (
            {
                "id": app_one.id,
                "fit_score": 88,
                "verdict": "strong_apply",
                "gaps": [],
                "comp_estimate": "22 LPA",
            },
            111,
        ),
        (
            {
                "id": app_two.id,
                "fit_score": 72,
                "verdict": "apply",
                "gaps": ["limited experimentation depth"],
                "comp_estimate": "18 LPA",
            },
            87,
        ),
    ]

    with patch(
        "api.routes.discovery.scorer_svc.score_job",
        new=AsyncMock(side_effect=scores),
    ) as score_mock:
        resp = await test_client.post("/discovery/score-batch", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {
        "scored": 2,
        "auto_approved": 1,
        "needs_review": 1,
    }
    assert score_mock.await_count == 2

    approved_queue = await test_client.get("/discovery/queue", headers=headers)
    assert approved_queue.status_code == 200
    assert [item["linkedin_job_id"] for item in approved_queue.json()["queue"]] == ["score-1"]

    app_one_row = await _get_app_by_external_id(user_id, "linkedin:score-1")
    app_two_row = await _get_app_by_external_id(user_id, "linkedin:score-2")
    assert app_one_row.status == "approved"
    assert app_one_row.fit_score == 88
    assert app_one_row.llm_tokens_used == 111
    assert app_one_row.scored_at is not None
    assert app_two_row.status == "scored"
    assert app_two_row.fit_score == 72
    assert app_two_row.verdict == "apply"
    assert app_two_row.gaps == ["limited experimentation depth"]


async def test_score_batch_scores_discovered_jobs_when_enrichment_did_not_complete(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    user_id = await _get_user_id(user_with_profile["user"]["email"])

    app_row = await _create_application(
        user_id,
        external_id="linkedin:score-discovered",
        title="ML Engineer",
        company="Good AI",
        status="discovered",
        description="",
        source="linkedin_extension",
    )

    with patch(
        "api.routes.discovery.scorer_svc.score_job",
        new=AsyncMock(
            return_value=(
                {
                    "id": app_row.id,
                    "fit_score": 76,
                    "verdict": "apply",
                    "gaps": ["description unavailable"],
                    "comp_estimate": "N/A",
                },
                42,
            )
        ),
    ) as score_mock:
        resp = await test_client.post("/discovery/score-batch", headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {
        "scored": 1,
        "auto_approved": 1,
        "needs_review": 0,
    }
    assert score_mock.await_count == 1

    app_row = await _get_app_by_external_id(user_id, "linkedin:score-discovered")
    assert app_row.status == "approved"
    assert app_row.fit_score == 76


async def test_queue_orders_results_by_fit_score_desc(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    user_id = await _get_user_id(user_with_profile["user"]["email"])

    await _create_application(
        user_id,
        external_id="linkedin:q-1",
        title="Highest Fit",
        status="approved",
        fit_score=96,
    )
    await _create_application(
        user_id,
        external_id="linkedin:q-2",
        title="Middle Fit",
        status="approved",
        fit_score=81,
    )
    await _create_application(
        user_id,
        external_id="linkedin:q-3",
        title="Lowest Fit",
        status="approved",
        fit_score=67,
    )

    resp = await test_client.get("/discovery/queue?limit=3", headers=headers)
    assert resp.status_code == 200
    queue = resp.json()["queue"]
    assert [item["title"] for item in queue] == ["Highest Fit", "Middle Fit", "Lowest Fit"]
    assert [item["fit_score"] for item in queue] == [96.0, 81.0, 67.0]


async def test_update_status_allows_valid_transitions(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    user_id = await _get_user_id(user_with_profile["user"]["email"])
    app_row = await _create_application(
        user_id,
        external_id="linkedin:status-1",
        status="approved",
    )

    applying_resp = await test_client.patch(
        f"/discovery/{app_row.id}/status",
        json={"status": "applying"},
        headers=headers,
    )
    assert applying_resp.status_code == 200
    assert applying_resp.json() == {"ok": True}

    applied_resp = await test_client.patch(
        f"/discovery/{app_row.id}/status",
        json={
            "status": "applied",
            "filled_fields_json": {"resume_uploaded": True, "work_auth": "Yes"},
        },
        headers=headers,
    )
    assert applied_resp.status_code == 200
    assert applied_resp.json() == {"ok": True}

    updated_row = await _get_app_by_external_id(user_id, "linkedin:status-1")
    assert updated_row.status == "applied"
    assert updated_row.filled_fields_json == {
        "resume_uploaded": True,
        "work_auth": "Yes",
    }
    assert updated_row.applied_at is not None

    invalid_resp = await test_client.patch(
        f"/discovery/{app_row.id}/status",
        json={"status": "not-a-real-status"},
        headers=headers,
    )
    assert invalid_resp.status_code == 422


async def test_approve_batch_approves_scored_jobs_above_threshold(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    user_id = await _get_user_id(user_with_profile["user"]["email"])

    await _create_application(
        user_id,
        external_id="linkedin:approve-1",
        title="Approve Me",
        status="scored",
        fit_score=92,
    )
    await _create_application(
        user_id,
        external_id="linkedin:approve-2",
        title="Approve Me Too",
        status="scored",
        fit_score=80,
    )
    await _create_application(
        user_id,
        external_id="linkedin:approve-3",
        title="Needs Review",
        status="scored",
        fit_score=79,
    )

    resp = await test_client.post(
        "/discovery/approve-batch",
        json={"min_score": 80},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() == {"approved": 2}

    queue_resp = await test_client.get("/discovery/queue?status=approved", headers=headers)
    assert queue_resp.status_code == 200
    assert [item["linkedin_job_id"] for item in queue_resp.json()["queue"]] == [
        "approve-1",
        "approve-2",
    ]

    below_threshold = await _get_app_by_external_id(user_id, "linkedin:approve-3")
    assert below_threshold.status == "scored"


async def test_stats_returns_dashboard_payload(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    user_id = await _get_user_id(user_with_profile["user"]["email"])

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = today_start.replace(day=1)

    recent_applied = [
        await _create_application(
            user_id,
            external_id=f"linkedin:recent-{idx}",
            company=company,
            title=f"Role {idx}",
            status="applied",
            fit_score=score,
            applied_at=now - timedelta(hours=idx),
            scored_at=week_start + timedelta(days=1),
        )
        for idx, (company, score) in enumerate(
            [
                ("Acme", 95),
                ("Beta", 75),
                ("Acme", 55),
                ("Gamma", 35),
                ("Acme", 82),
            ],
            start=1,
        )
    ]
    oldest_recent = await _create_application(
        user_id,
        external_id="linkedin:recent-6",
        company="Delta",
        title="Role 6",
        status="applied",
        fit_score=65,
        applied_at=now - timedelta(days=2),
        scored_at=week_start + timedelta(days=2),
    )
    await _create_application(
        user_id,
        external_id="linkedin:approved-queue",
        company="Queue Co",
        title="Approved Queue",
        status="approved",
        fit_score=88,
        scored_at=week_start + timedelta(days=1),
    )
    await _create_application(
        user_id,
        external_id="linkedin:needs-review",
        company="Review Co",
        title="Needs Review",
        status="scored",
        fit_score=45,
        scored_at=week_start + timedelta(days=1),
    )
    await _create_application(
        user_id,
        external_id="linkedin:discovered-only",
        company="Fresh Co",
        title="Fresh Discovery",
        status="discovered",
        fit_score=None,
        scored_at=week_start + timedelta(days=1),
    )
    await _create_application(
        user_id,
        external_id="linkedin:previous-week",
        company="Old Co",
        title="Old Week",
        status="applied",
        fit_score=90,
        applied_at=week_start - timedelta(days=1),
        scored_at=week_start - timedelta(days=1),
    )
    if month_start != week_start:
        await _create_application(
            user_id,
            external_id="linkedin:month-only",
            company="Month Co",
            title="Month Only",
            status="applied",
            fit_score=61,
            applied_at=month_start + timedelta(days=1),
            scored_at=month_start + timedelta(days=1),
        )

    resp = await test_client.get("/discovery/stats", headers=headers)
    assert resp.status_code == 200

    body = resp.json()
    assert body["applied_today"] >= 1
    assert body["applied_this_week"] == 6
    expected_month_count = 7 if month_start != week_start else 6
    expected_discovered_count = 9 if month_start != week_start else 8
    expected_scored_count = 8 if month_start != week_start else 7
    expected_good_count = 3 if month_start != week_start else 2
    assert body["applied_this_month"] == expected_month_count
    assert body["queue_approved"] == 1
    assert body["queue_needs_review"] == 1
    assert body["total_discovered_this_week"] == expected_discovered_count
    assert body["total_scored_this_week"] == expected_scored_count

    recent_ids = [item["id"] for item in body["recent_applications"]]
    assert len(recent_ids) == 5
    assert oldest_recent.id not in recent_ids
    assert recent_ids == [app.id for app in recent_applied]

    assert body["score_distribution"] == {
        "excellent": 4,
        "good": expected_good_count,
        "fair": 2,
        "poor": 1,
    }
    assert body["top_companies"][0] == {"company": "Acme", "count": 3}
