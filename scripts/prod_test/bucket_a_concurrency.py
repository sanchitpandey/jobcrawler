"""Bucket A — 13.4 Two-worker concurrency.

Slow Windows / SQLite path: bcrypt(rounds=14) is ~250-1000ms per register
locally. We use modest batch sizes so the test exercises real concurrency
across both worker processes without simply CPU-starving them.
"""
from __future__ import annotations
import concurrent.futures as cf
import json
import secrets
import sqlite3
import sys
import urllib.request
import urllib.error

API = "http://127.0.0.1:8768"
DB = "d:/AIML/jobcrawler/jobcrawler.db"
PW = "AStrongPassword!2026"
N = 8


def post(path: str, body: dict, ip: str) -> tuple[int, str]:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Forwarded-For": ip},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, repr(e)


# 13.4a — N concurrent registers of N distinct emails
print(f"[INFO] 13.4a: {N} concurrent registers of distinct emails")
emails = [f"conc-{i}-{secrets.token_hex(4)}@example.com" for i in range(N)]
with cf.ThreadPoolExecutor(max_workers=N) as ex:
    futs = [
        ex.submit(post, "/auth/register",
                  {"email": e, "password": PW}, f"10.130.{i}.1")
        for i, e in enumerate(emails)
    ]
    results = [f.result() for f in futs]
codes = [s for s, _ in results]
print(f"  status codes: {sorted(set(codes))}")
ok_codes = all(s == 202 for s in codes)
no_5xx = not any(s != -1 and 500 <= s < 600 for s in codes)
no_transport = -1 not in codes
print(f"  {'[PASS]' if ok_codes and no_5xx and no_transport else '[FAIL]'} 13.4a-no-server-errors: "
      f"no_5xx={no_5xx}, no_transport_errs={no_transport}, all_202={ok_codes}")

con = sqlite3.connect(DB)
n = con.execute(
    "SELECT COUNT(*) FROM users WHERE email IN ({})".format(
        ",".join(["?"] * len(emails))
    ),
    emails,
).fetchone()[0]
con.close()
print(f"  {'[PASS]' if n == N else '[FAIL]'} 13.4b-row-count: {n}/{N} distinct emails persisted")

# 13.4c — N concurrent registers of THE SAME email (race-safety)
print()
print(f"[INFO] 13.4c: {N} concurrent registers of THE SAME email")
same_email = f"race-{secrets.token_hex(4)}@example.com"
with cf.ThreadPoolExecutor(max_workers=N) as ex:
    futs = [
        ex.submit(post, "/auth/register",
                  {"email": same_email, "password": PW}, f"10.131.{i}.1")
        for i in range(N)
    ]
    results = [f.result() for f in futs]
codes = [s for s, _ in results]
print(f"  status codes: {sorted(set(codes))}")
con = sqlite3.connect(DB)
n = con.execute("SELECT COUNT(*) FROM users WHERE email=?", (same_email,)).fetchone()[0]
con.close()
no_5xx = not any(s != -1 and 500 <= s < 600 for s in codes)
ok = (n == 1) and no_5xx
print(f"  rows in DB: {n} (expected 1)")
print(f"  {'[PASS]' if ok else '[FAIL]'} 13.4c-no-duplicate-row")

# 13.4d — N concurrent logins of the distinct users from 13.4a
print()
print(f"[INFO] 13.4d: {N} concurrent logins across distinct users")
with cf.ThreadPoolExecutor(max_workers=N) as ex:
    futs = [
        ex.submit(post, "/auth/login",
                  {"email": e, "password": PW}, f"10.132.{i}.1")
        for i, e in enumerate(emails)
    ]
    results = [f.result() for f in futs]
codes = [s for s, _ in results]
print(f"  status codes: {sorted(set(codes))}")
ok = all(s == 200 for s in codes)
print(f"  {'[PASS]' if ok else '[FAIL]'} 13.4d-all-logins-ok")
