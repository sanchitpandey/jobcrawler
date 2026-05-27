"""Bucket A — 2.11 CSRF double-submit and 14.1 login throughput.

Runs against the live API on port 8767. Prints PASS/FAIL per check.
"""
from __future__ import annotations
from http import cookies as cookielib
import json
import secrets
import sys
import time
import urllib.request
import urllib.error

API = "http://127.0.0.1:8767"
IP = "10.111.0.1"
PW = "AStrongPassword!2026"


def call(method, path, body=None, headers=None, cookies=None):
    h = {"Content-Type": "application/json", "X-Forwarded-For": IP}
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode("utf-8", errors="replace")
            # email.message.Message: get_all preserves multiple Set-Cookie headers.
            set_cookies = r.headers.get_all("Set-Cookie") or []
            return r.status, set_cookies, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        set_cookies = e.headers.get_all("Set-Cookie") or []
        try:
            return e.code, set_cookies, json.loads(txt)
        except json.JSONDecodeError:
            return e.code, set_cookies, txt


def parse_set_cookie(set_cookies: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in set_cookies:
        c = cookielib.SimpleCookie(line)
        for name, m in c.items():
            out[name] = m.value
    return out


def make_user(tag: str) -> tuple[str, dict[str, str]]:
    """Register + login, return (email, set-cookies)."""
    email = f"qa-{tag}-{secrets.token_hex(4)}@example.com"
    s, _, _ = call("POST", "/auth/register", {"email": email, "password": PW})
    assert s == 202, s
    s, hdrs, body = call("POST", "/auth/login", {"email": email, "password": PW})
    assert s == 200, body
    return email, parse_set_cookie(hdrs)


# ── 2.11 CSRF double-submit ───────────────────────────────────────────────────
def test_csrf():
    email, cookies = make_user("csrf")
    refresh = cookies.get("jc_refresh")
    csrf = cookies.get("jc_csrf")
    assert refresh and csrf, f"login did not Set-Cookie jc_refresh/jc_csrf: {cookies}"

    # 2.11a — cookie path WITHOUT X-CSRF-Token → 403
    s, _, b = call("POST", "/auth/refresh", body={},
                   cookies={"jc_refresh": refresh, "jc_csrf": csrf})
    if s == 403 and "CSRF" in str(b).upper():
        print(f"[PASS] 2.11a-cookie-no-csrf-header: 403 {b}")
    else:
        print(f"[FAIL] 2.11a-cookie-no-csrf-header: got {s} {b}")

    # 2.11b — cookie + MISMATCHED header → 403
    s, _, b = call("POST", "/auth/refresh", body={},
                   cookies={"jc_refresh": refresh, "jc_csrf": csrf},
                   headers={"X-CSRF-Token": "wrong-token-here"})
    if s == 403:
        print(f"[PASS] 2.11b-cookie-mismatched-csrf: 403 {b}")
    else:
        print(f"[FAIL] 2.11b-cookie-mismatched-csrf: got {s} {b}")

    # 2.11c — cookie + MATCHING header → 200
    s, _, b = call("POST", "/auth/refresh", body={},
                   cookies={"jc_refresh": refresh, "jc_csrf": csrf},
                   headers={"X-CSRF-Token": csrf})
    if s == 200 and "access_token" in b:
        print(f"[PASS] 2.11c-cookie-matching-csrf: 200, new tokens issued")
        new_refresh = b.get("refresh_token")
    else:
        print(f"[FAIL] 2.11c-cookie-matching-csrf: got {s} {b}")
        new_refresh = refresh

    # 2.11d — body refresh (extension flow), NO cookie → bypasses CSRF, 200
    # Use the fresh refresh from 2.11c so the old one isn't burned.
    s, _, b = call("POST", "/auth/refresh", body={"refresh_token": new_refresh})
    if s == 200 and "access_token" in b:
        print(f"[PASS] 2.11d-body-refresh-no-csrf: 200 (extension flow)")
    else:
        print(f"[FAIL] 2.11d-body-refresh-no-csrf: got {s} {b}")

    # 2.11e — logout with cookie but no CSRF header → 403
    # First, log in fresh to get new cookies.
    _, fresh_cookies = make_user("csrf-logout")
    s, _, b = call("POST", "/auth/logout", body={},
                   cookies={"jc_refresh": fresh_cookies["jc_refresh"],
                            "jc_csrf": fresh_cookies["jc_csrf"]})
    if s == 403:
        print(f"[PASS] 2.11e-logout-cookie-no-csrf: 403")
    else:
        print(f"[FAIL] 2.11e-logout-cookie-no-csrf: got {s} {b}")


# ── 14.1 Login throughput ─────────────────────────────────────────────────────
def test_login_throughput():
    # Set up 30 fresh users (one per IP to dodge per-email throttle).
    print("[INFO] 14.1: provisioning 30 users …")
    users: list[tuple[str, str]] = []
    for i in range(30):
        ip = f"10.114.{i}.1"
        email = f"perf-{i}-{secrets.token_hex(4)}@example.com"
        h = {"X-Forwarded-For": ip, "Content-Type": "application/json"}
        req = urllib.request.Request(
            API + "/auth/register",
            data=json.dumps({"email": email, "password": PW}).encode(),
            headers=h, method="POST")
        urllib.request.urlopen(req, timeout=15).read()
        users.append((email, ip))
    # Time login latency, one at a time (no concurrency — just CPU cost).
    print("[INFO] 14.1: measuring login latency (30 serial logins)")
    times: list[float] = []
    for email, ip in users:
        h = {"X-Forwarded-For": ip, "Content-Type": "application/json"}
        req = urllib.request.Request(
            API + "/auth/login",
            data=json.dumps({"email": email, "password": PW}).encode(),
            headers=h, method="POST")
        t0 = time.perf_counter()
        urllib.request.urlopen(req, timeout=15).read()
        times.append(time.perf_counter() - t0)
    times.sort()
    p50 = times[len(times) // 2] * 1000
    p95 = times[int(len(times) * 0.95)] * 1000
    p99 = times[-1] * 1000
    mean = sum(times) / len(times) * 1000
    rps_ceiling = 1000 / mean
    if mean < 400:
        verdict = "PASS"
    else:
        verdict = "WARN"
    print(f"[{verdict}] 14.1-login-throughput: "
          f"mean={mean:.0f}ms p50={p50:.0f}ms p95={p95:.0f}ms p99={p99:.0f}ms "
          f"single-thread RPS ceiling ≈ {rps_ceiling:.1f}")
    print(f"        (bcrypt rounds=14 burns ~250ms/CPU per login — guide §14.1)")


if __name__ == "__main__":
    print("=== 2.11 CSRF double-submit ===")
    test_csrf()
    print()
    print("=== 14.1 Login throughput ===")
    test_login_throughput()
