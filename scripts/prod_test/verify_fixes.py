"""Verify B1/B2/B3 fixes via the live API on port 8766."""
import json
import secrets
import sqlite3
import sys
import urllib.request
import urllib.error

API = "http://127.0.0.1:8766"
ip = "10.250.0.1"


def http(method, path, body=None, headers=None):
    h = {"Content-Type": "application/json", "X-Forwarded-For": ip}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            txt = r.read().decode()
            return r.status, (json.loads(txt) if txt else {})
    except urllib.error.HTTPError as e:
        txt = e.read().decode()
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt


email = f"verify-{secrets.token_hex(4)}@example.com"
pw = "AStrongPassword!2026"
new_pw = "BrandNewPassword!2026X"

# Setup
http("POST", "/auth/register", {"email": email, "password": pw})
s, body = http("POST", "/auth/login", {"email": email, "password": pw})
assert s == 200, body
access = body["access_token"]
H = {"Authorization": f"Bearer {access}"}

print("=== B2: /auth/change-password ===")
# Wrong current → 403
s, b = http("POST", "/auth/change-password",
            {"current_password": "WrongPw!2026", "new_password": new_pw},
            headers=H)
print(f"wrong current_password: {s} {b}")
assert s == 403, f"expected 403, got {s}"
# Same password → 400
s, b = http("POST", "/auth/change-password",
            {"current_password": pw, "new_password": pw},
            headers=H)
print(f"same as current: {s} {b}")
assert s == 400, f"expected 400, got {s}"
# Short new password → 422
s, b = http("POST", "/auth/change-password",
            {"current_password": pw, "new_password": "short1!"},
            headers=H)
print(f"short new: {s}")
assert s == 422, f"expected 422, got {s}"
# Happy path
s, b = http("POST", "/auth/change-password",
            {"current_password": pw, "new_password": new_pw},
            headers=H)
print(f"change ok: {s}")
assert s == 204, f"expected 204, got {s} {b}"
# Login with old → 401
s, b = http("POST", "/auth/login", {"email": email, "password": pw})
print(f"login with OLD password: {s}")
assert s == 401, f"old pw should fail, got {s}"
# Login with new → 200
s, b = http("POST", "/auth/login", {"email": email, "password": new_pw})
print(f"login with NEW password: {s}")
assert s == 200, f"new pw should work, got {s} {b}"
print("B2 PASS")

# B3: status=discovered filter — verify the user, set up an app, query
print()
print("=== B3: /jobs?status=discovered filter ===")
con = sqlite3.connect("d:/AIML/jobcrawler/jobcrawler.db")
con.execute("UPDATE users SET is_verified=1 WHERE email=?", (email,))
con.commit()
con.close()
# Re-login to get a verified token
s, body = http("POST", "/auth/login", {"email": email, "password": new_pw})
H = {"Authorization": f"Bearer {body['access_token']}"}

# Filter by discovered — should be 200 now (not 422)
s, b = http("GET", "/jobs?status=discovered", headers=H)
print(f"GET /jobs?status=discovered: {s}")
assert s == 200, f"expected 200, got {s} {b}"
# Filter by enriched — also 200
s, b = http("GET", "/jobs?status=enriched", headers=H)
print(f"GET /jobs?status=enriched: {s}")
assert s == 200
# Still rejects invalid
s, b = http("GET", "/jobs?status=garbage", headers=H)
print(f"GET /jobs?status=garbage: {s} (should be 422)")
assert s == 422
print("B3 PASS")

print()
print("All live-API fix checks PASSED.")
