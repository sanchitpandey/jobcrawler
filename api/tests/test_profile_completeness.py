"""Integration tests for profile completeness checks."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_profile_completeness_reports_missing_fields(
    test_client: AsyncClient, auth_headers: dict
):
    resp = await test_client.get("/profile/completeness", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {
        "complete": False,
        "missing_fields": [
            "name",
            "email",
            "phone",
            "skills_json",
            "degree",
            "college",
            "graduation_year",
        ],
    }


async def test_profile_completeness_returns_complete_for_ready_profile(
    test_client: AsyncClient, user_with_profile: dict
):
    resp = await test_client.get(
        "/profile/completeness", headers=user_with_profile["headers"]
    )
    assert resp.status_code == 200
    assert resp.json() == {"complete": True, "missing_fields": []}
