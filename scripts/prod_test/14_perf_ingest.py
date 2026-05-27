"""Section 14.3 — Discovery ingest 500 jobs <2s."""
import json
import secrets
import sys
import time
import urllib.request
import sqlite3

API = "http://127.0.0.1:8765"
ip = "10.140.0.1"


def http(method, path, body=None, headers=None):
    h = {"Content-Type": "application/json", "X-Forwarded-For": ip}
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=h,
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, json.loads(r.read().decode())


email = f"perf-{secrets.token_hex(4)}@example.com"
pw = "AStrongPassword!2026"
http("POST", "/auth/register", {"email": email, "password": pw})
# verify directly in DB
con = sqlite3.connect("d:/AIML/jobcrawler/jobcrawler.db")
con.execute("UPDATE users SET is_verified=1, verification_token=NULL WHERE email=?", (email,))
con.commit()
con.close()
_, body = http("POST", "/auth/login", {"email": email, "password": pw})
H = {"Authorization": f"Bearer {body['access_token']}"}

jobs = [
    {"linkedin_job_id": f"perf-{i}", "title": f"Eng {i}",
     "company": "Co", "location": "Bengaluru",
     "url": f"https://lk/{i}"}
    for i in range(500)
]
t0 = time.perf_counter()
status, resp = http("POST", "/discovery/ingest", {"jobs": jobs}, headers=H)
dur = time.perf_counter() - t0
print(f"ingest_500: status={status} dur={dur:.2f}s "
      f"needs_enrichment={len(resp.get('needs_enrichment', []))} "
      f"filtered={resp.get('filtered_count')}")
sys.exit(0 if (status == 200 and dur < 2.0) else 1)
