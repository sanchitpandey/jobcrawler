"""Integration tests for profile CRUD endpoints."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

_FULL_PAYLOAD = {
    "name": "Sanchit Pandey",
    "email": "sanchit@example.com",
    "phone": "+91-9999999999",
    "college": "BITS Pilani",
    "degree": "B.E. EIE",
    "graduation_year": "2026",
    "cgpa": "7.15",
    "notice_period": "Available immediately",
    "total_experience": "1 year",
    "work_authorization": "Yes",
    "willing_to_relocate": "Yes",
    "willing_to_travel": "Yes",
    "sponsorship_required": "No",
    "skills": {"python_years": "3", "ml_years": "2"},
    "eeo": {"gender": "male", "ethnicity": "asian"},
    "candidate_summary": "Final-year student at BITS Pilani.",
    "preferred_roles": "ML Engineer, NLP Engineer",
    "target_locations": "Bengaluru, Remote",
}

_SAMPLE_MD = """\
# Apply Profile
## Personal
name: "Sanchit Pandey"
email: "md@example.com"
phone: "+91-9999999999"
linkedin: "https://linkedin.com/in/sanchit"
## Availability And Compensation
notice_period: "Available immediately"
## Education
degree: "B.E. EIE"
college: "BITS Pilani"
graduation_year: "2026"
cgpa: "7.15"
## Experience And Authorization
total_experience: "~1 year internship"
work_authorization: "Yes"
willing_to_relocate: "Yes"
## Technical Experience
python_years: "3"
ml_years: "2"
## Diversity Or EEO
gender: "male"
ethnicity: "asian"
## Candidate Summary
candidate_summary: >
  Final-year student at BITS Pilani.
"""


# ── GET /profile ──────────────────────────────────────────────────────────────

async def test_profile_not_found(test_client: AsyncClient, auth_headers: dict):
    resp = await test_client.get("/profile", headers=auth_headers)
    assert resp.status_code == 404


# ── POST /profile ─────────────────────────────────────────────────────────────

async def test_create_profile(test_client: AsyncClient, auth_headers: dict):
    resp = await test_client.post("/profile", json=_FULL_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Sanchit Pandey"
    assert body["college"] == "BITS Pilani"
    assert body["graduation_year"] == "2026"
    assert body["skills"]["python_years"] == "3"
    assert body["eeo"]["gender"] == "male"


async def test_create_profile_duplicate_returns_409(
    test_client: AsyncClient, auth_headers: dict
):
    await test_client.post("/profile", json=_FULL_PAYLOAD, headers=auth_headers)
    resp = await test_client.post("/profile", json=_FULL_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 409


# ── GET /profile after create ─────────────────────────────────────────────────

async def test_get_profile(test_client: AsyncClient, user_with_profile: dict):
    resp = await test_client.get("/profile", headers=user_with_profile["headers"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Test User"
    assert body["college"] == "BITS Pilani"
    assert body["skills"]["python_years"] == "3"


# ── PATCH /profile ────────────────────────────────────────────────────────────

async def test_update_profile(test_client: AsyncClient, user_with_profile: dict):
    headers = user_with_profile["headers"]
    resp = await test_client.patch(
        "/profile", json={"cgpa": "8.0", "skills": {"go_years": "1"}}, headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["cgpa"] == "8.0"
    # Skills merge — existing python_years still present
    assert body["skills"]["python_years"] == "3"
    assert body["skills"]["go_years"] == "1"


async def test_patch_creates_profile_if_missing(
    test_client: AsyncClient, auth_headers: dict
):
    """PATCH auto-creates a profile if one doesn't exist yet."""
    resp = await test_client.patch(
        "/profile", json={"name": "New User"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New User"


# ── POST /profile/import-markdown ─────────────────────────────────────────────

async def test_import_markdown(test_client: AsyncClient, auth_headers: dict):
    resp = await test_client.post(
        "/profile/import-markdown",
        content=_SAMPLE_MD.encode(),
        headers={**auth_headers, "Content-Type": "text/plain"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Sanchit Pandey"
    assert body["college"] == "BITS Pilani"
    assert body["graduation_year"] == "2026"
    assert body["skills"]["python_years"] == "3"
    assert body["eeo"]["gender"] == "male"


async def test_import_markdown_empty_body_returns_422(
    test_client: AsyncClient, auth_headers: dict
):
    resp = await test_client.post(
        "/profile/import-markdown",
        content=b"## No parseable fields here\n",
        headers={**auth_headers, "Content-Type": "text/plain"},
    )
    assert resp.status_code == 422


# ── Profile model helpers ─────────────────────────────────────────────────────

async def test_profile_to_dict(user_with_profile: dict):
    """to_dict() keys match what the legacy load_key_value_profile returns."""
    from api.models.profile import Profile

    p = Profile(
        user_id="u1",
        name="Alice",
        email="alice@example.com",
        college="MIT",
        graduation_year="2025",
        skills_json={"python_years": "5"},
        eeo_json={"gender": "female"},
        short_answers_json={"why_ml": "passion"},
        blacklist_companies=[],
        blacklist_keywords=[],
        min_comp_lpa=0,
        target_comp_lpa=0,
    )
    d = p.to_dict()
    assert d["name"] == "Alice"
    assert d["email"] == "alice@example.com"
    assert d["python_years"] == "5"   # skills merged at top level
    assert d["gender"] == "female"     # eeo merged at top level
    assert d["why_ml"] == "passion"    # short_answers merged at top level


async def test_profile_to_text(user_with_profile: dict):
    """to_text() includes expected section headers and values."""
    from api.models.profile import Profile

    p = Profile(
        user_id="u1",
        name="Alice",
        email="alice@example.com",
        college="MIT",
        graduation_year="2025",
        skills_json={"python_years": "5"},
        eeo_json={},
        short_answers_json={},
        blacklist_companies=[],
        blacklist_keywords=[],
        min_comp_lpa=0,
        target_comp_lpa=0,
    )
    text = p.to_text()
    assert "## Personal" in text
    assert "Alice" in text
    assert "## Education" in text
    assert "MIT" in text
    assert "## Technical Experience" in text
    assert 'python_years: "5"' in text
