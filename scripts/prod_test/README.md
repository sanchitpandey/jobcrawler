# scripts/prod_test/

Reusable scripts for running the live HTTP portion of `docs/PRODUCTION_TESTING.md`. Results land in `docs/TEST_RESULTS.md`.

## How to run

1. Bring the DB to head (creates if missing):
   ```bash
   conda run -n jobcrawler alembic -c api/alembic.ini upgrade head
   ```
2. Start the API in production mode in one terminal:
   ```bash
   APP_ENV=production DEBUG=false \
     JWT_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" \
     ALLOWED_ORIGINS='["https://jobcrawler.app","chrome-extension://abcdefghijklmnopabcdefghijklmnop"]' \
     ALLOWED_EXTENSION_IDS='["abcdefghijklmnopabcdefghijklmnop"]' \
     TRUSTED_PROXIES='["127.0.0.0/8"]' \
     DATABASE_URL="sqlite+aiosqlite:///./jobcrawler.db" \
     conda run -n jobcrawler python -m uvicorn api.main:app --host 127.0.0.1 --port 8765
   ```
3. Run each script (no args). Each one prints `[PASS]/[FAIL]` per check.

| Script | Covers |
|---|---|
| `01_validators.py` | 0.2 — Settings boot validators (in-process, no API needed) |
| `02_auth.py` | 2.1, 2.2, 2.3, 2.4, 2.5, 2.8, 2.9, 2.10, 2.12 |
| `03_to_08_main.py` | 3.1, 3.2, 3.3, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 5.1, 5.4, 5.6, 5.7, 6.1, 7.1, 7.6, 7.7, 8.1, 8.2 |
| `09_unique_constraints.py` | 9.2 — UNIQUE on email / razorpay_payment_id / webhook event_id (runs against `jobcrawler.db` directly) |
| `13_log_scrub.py` | 13.2 — RequestLoggingMiddleware leak check (in-process Starlette TestClient) |
| `14_perf_ingest.py` | 14.3 — Discovery ingest 500 jobs < 2s |

## Notes for future sessions

- `TRUSTED_PROXIES=127.0.0.0/8` lets the scripts send unique `X-Forwarded-For` headers so per-IP throttles don't fall over across many users.
- Email verification (`is_verified=1`) is set with a direct sqlite3 `UPDATE` rather than going through Resend. This is test-only.
- The free-tier weekly app cap is shared across the run; rerun after Monday 00:00 UTC or with a paid user if you hit it.
- Restart the API between full runs to clear in-memory rate-limit counters (or set `REDIS_URL` + flush keys).

For full context (what each item asserts and what counts as PASS/FAIL), read `docs/PRODUCTION_TESTING.md` alongside `docs/TEST_RESULTS.md`.
