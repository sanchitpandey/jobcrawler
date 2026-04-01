"""Tests for jobs tracking logic — no DB, no LLM."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from api.routes.jobs import (
    _app_to_response,
    _VALID_STATUSES,
    TrackJobRequest,
    StatusUpdateRequest,
)
from api.models.application import Application
from api.services.filter import make_id
from datetime import datetime, timezone


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_app(**kwargs) -> Application:
    defaults = dict(
        id="app-1",
        user_id="user-1",
        external_id="abc123",
        company="Acme",
        title="ML Engineer",
        location="Remote",
        url="https://example.com/job/1",
        description="Build LLMs.",
        ats_type="greenhouse",
        difficulty="hybrid",
        fit_score=82.0,
        comp_est="20 LPA",
        verdict="strong_apply",
        gaps=[],
        status="scored",
        cover_letter=None,
        filled_fields_json=None,
        applied_at=None,
        scored_model="llama-3.3-70b",
        llm_tokens_used=500,
    )
    defaults.update(kwargs)
    app = Application(**defaults)
    # Stamp timestamps that the DB would normally set via server_default
    app.__dict__.setdefault("scored_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    app.__dict__.setdefault("updated_at", datetime(2026, 1, 1, tzinfo=timezone.utc))
    return app


# ── _app_to_response ──────────────────────────────────────────────────────────

def test_app_to_response_maps_all_fields():
    app = _make_app()
    resp = _app_to_response(app)
    assert resp.id == "app-1"
    assert resp.company == "Acme"
    assert resp.fit_score == 82.0
    assert resp.verdict == "strong_apply"
    assert resp.status == "scored"
    assert resp.ats_type == "greenhouse"


def test_app_to_response_none_fields():
    app = _make_app(fit_score=None, verdict=None, cover_letter=None)
    resp = _app_to_response(app)
    assert resp.fit_score is None
    assert resp.verdict is None
    assert resp.cover_letter is None


# ── Valid statuses ────────────────────────────────────────────────────────────

def test_valid_statuses_contains_expected():
    for s in ("scored", "approved", "applying", "applied", "interview", "offer", "rejected"):
        assert s in _VALID_STATUSES


def test_invalid_status_not_in_set():
    assert "pending" not in _VALID_STATUSES
    assert "new" not in _VALID_STATUSES
    assert "" not in _VALID_STATUSES


# ── external_id / make_id deduplication ──────────────────────────────────────

def test_make_id_deterministic():
    id1 = make_id("Acme", "ML Engineer", "Remote")
    id2 = make_id("Acme", "ML Engineer", "Remote")
    assert id1 == id2
    assert len(id1) == 12


def test_make_id_differs_on_different_inputs():
    assert make_id("Acme", "ML Engineer", "Remote") != make_id("Acme", "SWE", "Remote")
    assert make_id("Acme", "ML Engineer", "Remote") != make_id("OtherCo", "ML Engineer", "Remote")


def test_make_id_case_insensitive():
    assert make_id("ACME", "ML Engineer", "Remote") == make_id("acme", "ml engineer", "remote")


# ── TrackJobRequest defaults ──────────────────────────────────────────────────

def test_track_job_request_defaults():
    req = TrackJobRequest(company="Acme", title="ML Engineer")
    assert req.location == ""
    assert req.url == ""
    assert req.fit_score is None
    assert req.verdict is None
    assert req.ats_type is None


def test_track_job_request_with_score():
    req = TrackJobRequest(
        company="Acme",
        title="ML Engineer",
        fit_score=85,
        verdict="strong_apply",
        gaps=["no Go experience"],
    )
    assert req.fit_score == 85
    assert req.gaps == ["no Go experience"]


# ── StatusUpdateRequest ───────────────────────────────────────────────────────

def test_status_update_request_optional_fields():
    req = StatusUpdateRequest(status="applied")
    assert req.filled_fields_json is None
    assert req.cover_letter is None


def test_status_update_with_audit_data():
    req = StatusUpdateRequest(
        status="applied",
        filled_fields_json={"years_experience": "2"},
        cover_letter="Dear hiring manager...",
    )
    assert req.filled_fields_json == {"years_experience": "2"}
    assert req.cover_letter.startswith("Dear")


# ── forms.py schemas ──────────────────────────────────────────────────────────

def test_generate_cover_schemas_importable():
    from api.routes.forms import GenerateCoverRequest, GenerateCoverResponse
    req = GenerateCoverRequest(company="Acme", title="ML Engineer", description="Build stuff.")
    assert req.location == ""
    resp = GenerateCoverResponse(cover_letter="Dear hiring manager...")
    assert "Dear" in resp.cover_letter


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
