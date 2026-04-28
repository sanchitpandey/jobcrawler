"""
End-to-end smoke test against a running API instance.

Usage:
    API_URL=https://api.jobcrawler.app python scripts/smoke_test.py
    API_URL=http://localhost:8000 python scripts/smoke_test.py  # default
"""

import os
import sys
import uuid
import json
import urllib.request
import urllib.error

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

results: list[tuple[str, bool, str]] = []


def _request(
    method: str,
    path: str,
    body: dict | None = None,
    token: str | None = None,
    form: bool = False,
) -> tuple[int, dict]:
    url = f"{API_URL}{path}"
    headers: dict[str, str] = {}

    if form and body:
        data = urllib.parse.urlencode(body).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    else:
        data = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            return e.code, json.loads(body_text)
        except Exception:
            return e.code, {"_raw": body_text}


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((name, condition, detail))
    icon = PASS if condition else FAIL
    print(f"  {icon} {name}" + (f"  [{detail}]" if detail else ""))


def run() -> None:
    import urllib.parse  # noqa: F401 — needed for form encoding

    print(f"\nSmoke test → {API_URL}\n")

    # ── 1. Health check ───────────────────────────────────────────────────────
    print("1. Health check")
    code, body = _request("GET", "/health")
    check("GET /health returns 200", code == 200, f"got {code}")
    check("status == ok", body.get("status") == "ok", str(body.get("status")))
    check("db == connected", body.get("db") == "connected", str(body.get("db")))

    # ── 2. Register ───────────────────────────────────────────────────────────
    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    password = "SmokeTest123!"
    print(f"\n2. Register ({email})")
    code, body = _request("POST", "/auth/register", {"email": email, "password": password})
    check("POST /auth/register returns 201", code == 201, f"got {code}")
    access_token: str = body.get("access_token", "")
    check("access_token present", bool(access_token))

    if not access_token:
        print("\n  Cannot continue without a token — aborting.\n")
        _print_summary()
        sys.exit(1)

    # ── 3. Login ──────────────────────────────────────────────────────────────
    print("\n3. Login")
    code, body = _request(
        "POST", "/auth/login", {"username": email, "password": password}, form=True
    )
    check("POST /auth/login returns 200", code == 200, f"got {code}")
    login_token: str = body.get("access_token", "")
    check("access_token present", bool(login_token))
    token = login_token or access_token

    # ── 4. Create profile ─────────────────────────────────────────────────────
    print("\n4. Create profile")
    profile_payload = {
        "name": "Smoke Test User",
        "email": email,
        "phone": "+91-9000000000",
        "college": "Test University",
        "degree": "B.Tech CS",
        "graduation_year": "2025",
        "cgpa": "8.0",
        "notice_period": "Available immediately",
        "total_experience": "0 years",
        "work_authorization": "Yes",
        "willing_to_relocate": "Yes",
        "willing_to_travel": "No",
        "sponsorship_required": "No",
        "candidate_summary": "Smoke test user for API verification.",
        "preferred_roles": "Software Engineer",
        "target_locations": "Remote",
    }
    code, body = _request("POST", "/profile", profile_payload, token=token)
    check("POST /profile returns 201", code == 201, f"got {code}")
    check("profile.name correct", body.get("name") == "Smoke Test User")

    # ── 5. Score a job ────────────────────────────────────────────────────────
    print("\n5. Score job")
    job_payload = {
        "id": f"smoke-{uuid.uuid4().hex[:8]}",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "location": "Remote",
        "description": "We are looking for a software engineer with Python experience.",
        "is_remote": True,
    }
    code, body = _request("POST", "/jobs/score-job", job_payload, token=token)
    check("POST /jobs/score-job returns 200", code == 200, f"got {code}")
    check("fit_score present", "fit_score" in body, str(body.keys()))
    check("verdict present", "verdict" in body)

    # ── 6. Answer form fields ─────────────────────────────────────────────────
    print("\n6. Answer form fields")
    fields_payload = {
        "fields": [
            {"label": "Years of experience", "field_type": "text"},
            {"label": "Are you authorized to work?", "field_type": "radio", "options": ["Yes", "No"]},
        ],
        "company": "Acme Corp",
        "job_title": "Software Engineer",
    }
    code, body = _request("POST", "/forms/answer-fields", fields_payload, token=token)
    check("POST /forms/answer-fields returns 200", code == 200, f"got {code}")
    check("answers array present", "answers" in body)
    check("correct answer count", len(body.get("answers", [])) == 2)

    # ── 7. Check usage ────────────────────────────────────────────────────────
    print("\n7. Usage")
    code, body = _request("GET", "/jobs/usage", token=token)
    check("GET /jobs/usage returns 200", code == 200, f"got {code}")
    check("used field present", "used" in body)
    check("limit field present", "limit" in body)

    _print_summary()


def _print_summary() -> None:
    total = len(results)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = total - passed
    print(f"\n{'─' * 40}")
    print(f"Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  ({failed} FAILED)", end="")
        print()
        sys.exit(1)
    else:
        print("  — all good!")


if __name__ == "__main__":
    import urllib.parse
    run()
