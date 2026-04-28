"""Integration tests for discovery search preference routes."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_search_preferences_crud(
    test_client: AsyncClient, registered_user: dict
):
    headers = {"Authorization": f"Bearer {registered_user['tokens']['access_token']}"}

    get_missing = await test_client.get("/discovery/preferences", headers=headers)
    assert get_missing.status_code == 404
    assert get_missing.json()["detail"] == "No search preferences set"

    create_payload = {
        "keywords": ["ml engineer", "nlp engineer"],
        "location": "Bengaluru",
        "experience_levels": "2,3",
        "remote_filter": "2",
        "time_range": "r604800",
        "auto_apply_threshold": 78,
        "max_daily_applications": 12,
        "skip_companies": ["Blocked Co"],
        "skip_title_keywords": ["staff", "principal"],
    }
    create_resp = await test_client.post(
        "/discovery/preferences",
        json=create_payload,
        headers=headers,
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    assert created["keywords"] == ["ml engineer", "nlp engineer"]
    assert created["location"] == "Bengaluru"
    assert created["auto_apply_threshold"] == 78
    assert created["max_daily_applications"] == 12
    assert created["skip_companies"] == ["Blocked Co"]
    assert created["skip_title_keywords"] == ["staff", "principal"]
    pref_id = created["id"]

    get_created = await test_client.get("/discovery/preferences", headers=headers)
    assert get_created.status_code == 200
    assert get_created.json() == created

    update_resp = await test_client.post(
        "/discovery/preferences",
        json={
            "keywords": ["applied scientist"],
            "location": "Remote",
            "experience_levels": "4",
            "remote_filter": "3",
            "time_range": "r86400",
            "auto_apply_threshold": 85,
            "max_daily_applications": 8,
            "skip_companies": ["Another Co"],
            "skip_title_keywords": ["intern"],
        },
        headers=headers,
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["id"] == pref_id
    assert updated["keywords"] == ["applied scientist"]
    assert updated["location"] == "Remote"
    assert updated["experience_levels"] == "4"
    assert updated["remote_filter"] == "3"
    assert updated["auto_apply_threshold"] == 85
    assert updated["max_daily_applications"] == 8
    assert updated["skip_companies"] == ["Another Co"]
    assert updated["skip_title_keywords"] == ["intern"]

    get_updated = await test_client.get("/discovery/preferences", headers=headers)
    assert get_updated.status_code == 200
    assert get_updated.json() == updated
