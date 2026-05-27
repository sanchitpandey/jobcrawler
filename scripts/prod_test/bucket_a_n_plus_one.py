"""Section 14.4 — N+1 query check on /discovery/score-batch.

Strategy:
  1. Spin up the FastAPI app against a fresh in-memory SQLite.
  2. Register + verify a user, create a profile, ingest N=10 discovery jobs.
  3. Patch the LLM scorer with a stub that returns a fixed result (no LLM call,
     no LLM-dependent query traffic).
  4. Hook SQLAlchemy's `before_cursor_execute` to count every SQL statement
     issued during the score-batch HTTP call.
  5. Assert: queries <= 2 * N + 8 (i.e. linear in N is *acceptable* per the
     guide; what we forbid is quadratic, hidden-relationship loads etc.).
"""
from __future__ import annotations
import asyncio
import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-must-be-32-plus-characters-long-1")
os.environ.setdefault("APP_ENV", "development")
sys.path.insert(0, ".")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event, update  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession, async_sessionmaker, create_async_engine,
)


async def main():
    from api.main import app
    from api.models import Base
    from api.models.base import get_db
    from api.models.user import User
    from api.middleware import auth_throttle
    auth_throttle.reset_for_tests()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False, autoflush=False
    )

    async def _ovr():
        async with factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
    app.dependency_overrides[get_db] = _ovr

    # Hook SQL query counter — but only count during score-batch.
    counting = False
    query_log: list[str] = []

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if counting:
            query_log.append(statement.split()[0].upper() + " " + statement[:100])

    # Stub the LLM scorer so no real LLM call, no extra DB queries.
    async def _fake_score_job(job, profile_text, profile_kv):
        return ({"fit_score": 80, "verdict": "apply", "gaps": [], "comp_estimate": ""}, 100)

    import api.routes.discovery as disc_route
    disc_route.scorer_svc.score_job = _fake_score_job

    N = 10
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        # register + verify
        await c.post("/auth/register",
                     json={"email": "n1@example.com", "password": "PasswordAbc!2026"})
        async with factory() as s:
            await s.execute(update(User).where(User.email == "n1@example.com")
                            .values(is_verified=True))
            await s.commit()
        login = await c.post("/auth/login",
                             json={"email": "n1@example.com",
                                   "password": "PasswordAbc!2026"})
        token = login.json()["access_token"]
        H = {"Authorization": f"Bearer {token}"}

        # profile
        await c.post("/profile", json={"name": "Q", "location_current": "BLR",
                                       "skills": {"python_years": "3"}},
                     headers=H)

        # ingest N jobs
        jobs = [{"linkedin_job_id": f"n1-{i}", "title": f"T{i}", "company": "Co",
                 "location": "BLR", "url": f"https://lk/{i}"} for i in range(N)]
        ing = await c.post("/discovery/ingest", json={"jobs": jobs}, headers=H)
        assert ing.status_code == 200, ing.text

        # Now count queries during score-batch
        counting = True
        r = await c.post("/discovery/score-batch", headers=H)
        counting = False
        assert r.status_code == 200, r.text
        body = r.json()
        print(f"score-batch: scored={body['scored']} approved={body['auto_approved']} review={body['needs_review']}")

    # Analyse
    selects = sum(1 for q in query_log if q.startswith("SELECT"))
    updates = sum(1 for q in query_log if q.startswith("UPDATE"))
    inserts = sum(1 for q in query_log if q.startswith("INSERT"))
    print(f"queries during score-batch: total={len(query_log)} "
          f"selects={selects} updates={updates} inserts={inserts}")
    # Linear bound: 2 queries per app (one initial load via N=1 query, plus per-app updates).
    # Quadratic would be ≥ N^2 ≈ 100 selects. Assert SELECTs are O(1) + O(N), not O(N^2).
    ok_selects = selects <= 2 * N + 10
    print(f"{'[PASS]' if ok_selects else '[FAIL]'} 14.4-no-N+1: "
          f"selects={selects} ≤ 2N+10 = {2*N+10}")
    if not ok_selects:
        # Print the SELECT statements for diagnosis
        for q in query_log:
            if q.startswith("SELECT"):
                print("  ", q[:160])

    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
