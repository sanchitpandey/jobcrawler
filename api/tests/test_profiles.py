"""Tests for api/routes/profiles.py — parser and mapping logic (no DB)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from api.routes.profiles import (
    _parse_markdown_profile,
    _kv_to_profile,
    _apply_payload,
    ProfilePayload,
    _SCALAR_KEY_MAP,
    _SKILLS_KEYS,
    _EEO_KEYS,
)
from api.models.profile import Profile


SAMPLE_MD = """\
# Apply Profile
## Personal
name: "Sanchit Pandey"
email: "test@example.com"
phone: "+91-9999999999"
linkedin: "https://linkedin.com/in/sanchit"
github: "https://github.com/sanchit"
portfolio: "https://sanchit.dev"
location_current: "Hyderabad, India"
## Availability And Compensation
notice_period: "Available immediately"
current_ctc: "0"
expected_ctc: "1500000"
expected_ctc_min_lpa: "12"
start_date: "2026-05"
## Education
degree: "B.E. EIE"
college: "BITS Pilani"
graduation_month_year: "May 2026"
graduation_year: "2026"
cgpa: "7.15"
## Experience And Authorization
total_experience: "~1 year internship"
work_authorization: "Yes"
willing_to_relocate: "Yes"
willing_to_travel: "Yes"
sponsorship_required: "No"
## Technical Experience
python_years: "3"
ml_years: "2"
llm_nlp_rag_years: "2"
pytorch_years: "2"
huggingface_years: "1"
## Diversity Or EEO
gender: "male"
ethnicity: "asian"
veteran_status: "no"
disability: "no"
## Job Search Preferences
preferred_roles: >
  ML Engineer, NLP Engineer
target_locations: >
  Bengaluru, Remote
must_have_preferences: >
  LLMs, RAG
deal_breakers: >
  No ML component
## Candidate Summary
candidate_summary: >
  Final-year student at BITS Pilani.
experience_highlights: >
  ACL ARR 2026 submission.
## Short Answers
why_ml_engineering: >
  I love building things that matter.
"""


# ── _parse_markdown_profile ───────────────────────────────────────────────────

def test_parse_scalar_fields():
    kv = _parse_markdown_profile(SAMPLE_MD)
    assert kv["name"] == "Sanchit Pandey"
    assert kv["email"] == "test@example.com"
    assert kv["linkedin"] == "https://linkedin.com/in/sanchit"
    assert kv["cgpa"] == "7.15"
    assert kv["graduation_year"] == "2026"


def test_parse_multiline_fields():
    kv = _parse_markdown_profile(SAMPLE_MD)
    assert "ML Engineer" in kv["preferred_roles"]
    assert "BITS Pilani" in kv["candidate_summary"]
    assert "ACL ARR" in kv["experience_highlights"]
    assert "I love building" in kv["why_ml_engineering"]


def test_parse_skills_and_eeo():
    kv = _parse_markdown_profile(SAMPLE_MD)
    assert kv["python_years"] == "3"
    assert kv["ml_years"] == "2"
    assert kv["gender"] == "male"
    assert kv["ethnicity"] == "asian"


def test_parse_empty_string_returns_empty():
    assert _parse_markdown_profile("") == {}


def test_parse_ignores_comment_and_section_headers():
    kv = _parse_markdown_profile(SAMPLE_MD)
    # Section headers like "## Personal" should not appear as keys
    assert "Personal" not in kv
    assert "Technical Experience" not in kv


# ── _kv_to_profile ────────────────────────────────────────────────────────────

def _make_profile() -> Profile:
    # SQLAlchemy models are safe to instantiate without a session
    return Profile(
        user_id="test-user",
        skills_json={},
        eeo_json={},
        short_answers_json={},
        blacklist_companies=[],
        blacklist_keywords=[],
        min_comp_lpa=0,
        target_comp_lpa=0,
    )


def test_kv_to_profile_scalar_mapping():
    kv = _parse_markdown_profile(SAMPLE_MD)
    profile = _make_profile()
    _kv_to_profile(kv, profile)
    assert profile.name == "Sanchit Pandey"
    assert profile.email == "test@example.com"
    assert profile.linkedin_url == "https://linkedin.com/in/sanchit"
    assert profile.graduation_year == "2026"


def test_kv_to_profile_skills_json():
    kv = _parse_markdown_profile(SAMPLE_MD)
    profile = _make_profile()
    _kv_to_profile(kv, profile)
    assert profile.skills_json["python_years"] == "3"
    assert profile.skills_json["pytorch_years"] == "2"


def test_kv_to_profile_eeo_json():
    kv = _parse_markdown_profile(SAMPLE_MD)
    profile = _make_profile()
    _kv_to_profile(kv, profile)
    assert profile.eeo_json["gender"] == "male"
    assert profile.eeo_json["disability"] == "no"


def test_kv_to_profile_short_answers():
    kv = _parse_markdown_profile(SAMPLE_MD)
    profile = _make_profile()
    _kv_to_profile(kv, profile)
    assert "why_ml_engineering" in profile.short_answers_json
    assert "I love building" in profile.short_answers_json["why_ml_engineering"]


def test_kv_to_profile_merges_existing_skills():
    kv = {"python_years": "4"}
    profile = _make_profile()
    profile.skills_json = {"ml_years": "2"}
    _kv_to_profile(kv, profile)
    assert profile.skills_json["python_years"] == "4"
    assert profile.skills_json["ml_years"] == "2"  # preserved


# ── _apply_payload ────────────────────────────────────────────────────────────

def test_apply_payload_sets_scalar():
    profile = _make_profile()
    payload = ProfilePayload(name="Alice", email="alice@example.com", cgpa="8.5")
    _apply_payload(profile, payload)
    assert profile.name == "Alice"
    assert profile.email == "alice@example.com"
    assert profile.cgpa == "8.5"


def test_apply_payload_ignores_none_fields():
    profile = _make_profile()
    profile.name = "Original"
    payload = ProfilePayload(email="new@example.com")  # name is None
    _apply_payload(profile, payload)
    assert profile.name == "Original"  # untouched
    assert profile.email == "new@example.com"


def test_apply_payload_merges_skills_dict():
    profile = _make_profile()
    profile.skills_json = {"python_years": "3"}
    payload = ProfilePayload(skills={"ml_years": "2"})
    _apply_payload(profile, payload)
    assert profile.skills_json["python_years"] == "3"
    assert profile.skills_json["ml_years"] == "2"


def test_apply_payload_overwrites_skills_key():
    profile = _make_profile()
    profile.skills_json = {"python_years": "3"}
    payload = ProfilePayload(skills={"python_years": "5"})
    _apply_payload(profile, payload)
    assert profile.skills_json["python_years"] == "5"


def test_apply_payload_blacklist_lists():
    profile = _make_profile()
    payload = ProfilePayload(
        blacklist_companies=["BadCo", "Staffing Inc"],
        blacklist_keywords=["unpaid"],
    )
    _apply_payload(profile, payload)
    assert profile.blacklist_companies == ["BadCo", "Staffing Inc"]
    assert profile.blacklist_keywords == ["unpaid"]


# ── Key mapping completeness ──────────────────────────────────────────────────

def test_all_scalar_map_targets_exist_on_model():
    """Every value in _SCALAR_KEY_MAP should be a real column on Profile."""
    cols = {col.name for col in Profile.__table__.columns}
    for md_key, col_name in _SCALAR_KEY_MAP.items():
        assert col_name in cols, f"_SCALAR_KEY_MAP[{md_key!r}] -> {col_name!r} not in Profile columns"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
