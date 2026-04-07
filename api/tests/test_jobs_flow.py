"""Integration tests for job tracking and scoring endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_JOB_PAYLOAD = {
    "company": "Acme AI",
    "title": "ML Engineer",
    "location": "Remote",
    "url": "https://example.com/job/1",
    "description": "Build production ML pipelines.",
    "ats_type": "greenhouse",
}

_SCORE_RESPONSE = {
    "id": "job-abc",
    "fit_score": 82,
    "comp_estimate": "18 LPA",
    "verdict": "strong_apply",
    "gaps": ["no Go experience"],
    "why": "Strong Python/ML match.",
}


# ── POST /jobs ────────────────────────────────────────────────────────────────

async def test_track_job(test_client: AsyncClient, user_with_profile: dict):
    resp = await test_client.post(
        "/jobs", json=_JOB_PAYLOAD, headers=user_with_profile["headers"]
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["company"] == "Acme AI"
    assert body["title"] == "ML Engineer"
    assert body["status"] in ("scored", "new")
    assert "id" in body


async def test_track_job_idempotent(test_client: AsyncClient, user_with_profile: dict):
    """Tracking the same job twice returns the existing record, not a duplicate."""
    headers = user_with_profile["headers"]
    r1 = await test_client.post("/jobs", json=_JOB_PAYLOAD, headers=headers)
    r2 = await test_client.post("/jobs", json=_JOB_PAYLOAD, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]


async def test_track_job_requires_auth(test_client: AsyncClient):
    resp = await test_client.post("/jobs", json=_JOB_PAYLOAD)
    assert resp.status_code == 401


# ── GET /jobs ─────────────────────────────────────────────────────────────────

async def test_list_jobs_empty(test_client: AsyncClient, user_with_profile: dict):
    resp = await test_client.get("/jobs", headers=user_with_profile["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_list_jobs(test_client: AsyncClient, user_with_profile: dict):
    headers = user_with_profile["headers"]
    await test_client.post("/jobs", json=_JOB_PAYLOAD, headers=headers)
    resp = await test_client.get("/jobs", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["company"] == "Acme AI"


async def test_list_jobs_filter_status(test_client: AsyncClient, user_with_profile: dict):
    headers = user_with_profile["headers"]
    # Track a job with fit_score so it gets status="scored"
    await test_client.post(
        "/jobs",
        json={**_JOB_PAYLOAD, "fit_score": 82, "verdict": "strong_apply"},
        headers=headers,
    )

    # Filter matches
    resp = await test_client.get("/jobs?status=scored", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # Filter no match
    resp = await test_client.get("/jobs?status=applied", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_list_jobs_invalid_status(test_client: AsyncClient, user_with_profile: dict):
    resp = await test_client.get(
        "/jobs?status=invalid_status", headers=user_with_profile["headers"]
    )
    assert resp.status_code == 422


# ── PATCH /jobs/{id}/status ───────────────────────────────────────────────────

async def test_update_status(test_client: AsyncClient, user_with_profile: dict):
    headers = user_with_profile["headers"]
    create_resp = await test_client.post("/jobs", json=_JOB_PAYLOAD, headers=headers)
    app_id = create_resp.json()["id"]

    resp = await test_client.patch(
        f"/jobs/{app_id}/status", json={"status": "approved"}, headers=headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"


async def test_update_status_applied_sets_timestamp(
    test_client: AsyncClient, user_with_profile: dict
):
    headers = user_with_profile["headers"]
    create_resp = await test_client.post("/jobs", json=_JOB_PAYLOAD, headers=headers)
    app_id = create_resp.json()["id"]

    resp = await test_client.patch(
        f"/jobs/{app_id}/status", json={"status": "applied"}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "applied"
    assert body["applied_at"] is not None


async def test_update_status_invalid(test_client: AsyncClient, user_with_profile: dict):
    headers = user_with_profile["headers"]
    create_resp = await test_client.post("/jobs", json=_JOB_PAYLOAD, headers=headers)
    app_id = create_resp.json()["id"]

    resp = await test_client.patch(
        f"/jobs/{app_id}/status", json={"status": "nonexistent"}, headers=headers
    )
    assert resp.status_code == 422


async def test_update_status_other_user_returns_404(
    test_client: AsyncClient, user_with_profile: dict
):
    """Cannot update another user's application."""
    headers = user_with_profile["headers"]
    create_resp = await test_client.post("/jobs", json=_JOB_PAYLOAD, headers=headers)
    app_id = create_resp.json()["id"]

    # Register a second user
    r = await test_client.post(
        "/auth/register", json={"email": "other@example.com", "password": "otherpass1"}
    )
    other_token = r.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}

    resp = await test_client.patch(
        f"/jobs/{app_id}/status", json={"status": "applied"}, headers=other_headers
    )
    assert resp.status_code == 404


# ── POST /jobs/score-job ──────────────────────────────────────────────────────

async def test_score_job(test_client: AsyncClient, user_with_profile: dict):
    """Score-job calls LLM — mock it to avoid external calls."""
    mock_scored = {
        "id": "job-abc",
        "fit_score": 82,
        "comp_estimate": "18 LPA",
        "verdict": "strong_apply",
        "gaps": ["no Go experience"],
        "why": "Strong Python/ML match.",
    }

    with patch(
        "api.routes.jobs.score_job", new_callable=AsyncMock, return_value=(mock_scored, 100)
    ):
        resp = await test_client.post(
            "/jobs/score-job",
            json={
                "id": "job-abc",
                "title": "ML Engineer",
                "company": "Acme AI",
                "description": "Build ML pipelines.",
            },
            headers=user_with_profile["headers"],
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["fit_score"] == 82
    assert body["verdict"] == "strong_apply"
    assert body["gaps"] == ["no Go experience"]


async def test_score_job_requires_profile(
    test_client: AsyncClient, auth_headers: dict
):
    """score-job returns 404 when user has no profile."""
    resp = await test_client.post(
        "/jobs/score-job",
        json={
            "id": "job-xyz",
            "title": "ML Engineer",
            "company": "Acme AI",
            "description": "Build ML pipelines.",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 404
