from __future__ import annotations

import argparse
import random
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from config import AUTO_APPLY_DELAY, DB_PATH, MAX_APPLIES_PER_RUN
from indeed_apply import IndeedApplyBot
from linkedin_apply import ApplyResult, LinkedInApplyBot

Path("output").mkdir(exist_ok=True)


def get_approved_jobs(limit: int = 100) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, company, title, location, url, fit_score, comp_est, verdict, gaps
        FROM jobs
        WHERE status = 'approved'
        ORDER BY fit_score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def set_status(job_id: str, status: str, notes: str = "") -> None:
    conn = sqlite3.connect(DB_PATH)
    if status == "applied":
        conn.execute(
            "UPDATE jobs SET status='applied', applied_at=? WHERE id=?",
            (datetime.now().isoformat(), job_id),
        )
    else:
        conn.execute(
            "UPDATE jobs SET status=?, gaps=? WHERE id=?",
            (status, notes, job_id),
        )
    conn.commit()
    conn.close()


def _platform_of(url: str) -> str:
    url = url.lower()
    if "linkedin.com" in url:
        return "linkedin"
    if "indeed.com" in url:
        return "indeed"
    return "unknown"


def _log(job: dict, result: ApplyResult) -> None:
    icon = {
        "applied": "[OK]",
        "already_applied": "[SKIP]",
        "manual_review": "[FLAG]",
        "error": "[X]",
    }.get(result.status, "[?]")
    print(
        f"  {icon} [{job['fit_score']:>3.0f}] "
        f"{job['company']:<25} {job['title'][:35]:<35} "
        f"-> {result.status}"
    )
    if result.manual_questions:
        for question in result.manual_questions[:3]:
            print(f"       Manual: {question[:80]}")
    if result.error_message:
        print(f"       Error:  {result.error_message[:120]}")


def run(dry_run: bool = False, headless: bool = True, limit: int = MAX_APPLIES_PER_RUN) -> None:
    jobs = get_approved_jobs(limit=limit)
    if not jobs:
        print("No approved jobs found. Run the review server first (python review_server.py).")
        return

    linkedin_jobs = [job for job in jobs if _platform_of(job["url"]) == "linkedin"]
    indeed_jobs = [job for job in jobs if _platform_of(job["url"]) == "indeed"]
    unknown_jobs = [job for job in jobs if _platform_of(job["url"]) == "unknown"]

    print("\n" + "=" * 55)
    print(f"  AUTO-APPLY  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)
    print(
        f"  Approved: {len(jobs)} jobs "
        f"(LinkedIn: {len(linkedin_jobs)}, Indeed: {len(indeed_jobs)}, Unknown: {len(unknown_jobs)})"
    )
    if dry_run:
        print("  DRY RUN - no applications will be submitted\n")

    stats = {"applied": 0, "already_applied": 0, "manual_review": 0, "error": 0}

    if linkedin_jobs:
        print(f"\n> LinkedIn ({len(linkedin_jobs)} jobs)")
        with LinkedInApplyBot(headless=headless) as bot:
            if not bot.login():
                print("  [X] LinkedIn login failed - skipping LinkedIn jobs")
            else:
                for job in linkedin_jobs:
                    if dry_run:
                        print(f"  [DRY] {job['company']:<25} {job['title'][:40]}")
                        continue

                    result = bot.apply(job_url=job["url"], company=job["company"], title=job["title"])
                    _log(job, result)
                    stats[result.status] = stats.get(result.status, 0) + 1

                    if result.status == "applied":
                        set_status(job["id"], "applied")
                    elif result.status == "manual_review":
                        notes = " | ".join(result.manual_questions[:5])
                        set_status(job["id"], "manual_review", notes)
                    elif result.status == "already_applied":
                        set_status(job["id"], "applied")
                    else:
                        set_status(job["id"], "error", result.error_message)

                    delay = random.uniform(*AUTO_APPLY_DELAY)
                    print(f"       (waiting {delay:.1f}s)")
                    time.sleep(delay)

    if indeed_jobs:
        print(f"\n> Indeed ({len(indeed_jobs)} jobs)")
        with IndeedApplyBot(headless=headless) as bot:
            if not bot.login():
                print("  [X] Indeed login failed - skipping Indeed jobs")
            else:
                for job in indeed_jobs:
                    if dry_run:
                        print(f"  [DRY] {job['company']:<25} {job['title'][:40]}")
                        continue

                    result = bot.apply(job_url=job["url"], company=job["company"], title=job["title"])
                    _log(job, result)
                    stats[result.status] = stats.get(result.status, 0) + 1

                    if result.status == "applied":
                        set_status(job["id"], "applied")
                    elif result.status == "manual_review":
                        notes = " | ".join(result.manual_questions[:5])
                        set_status(job["id"], "manual_review", notes)
                    elif result.status == "already_applied":
                        set_status(job["id"], "applied")
                    else:
                        set_status(job["id"], "error", result.error_message)

                    delay = random.uniform(*AUTO_APPLY_DELAY)
                    print(f"       (waiting {delay:.1f}s)")
                    time.sleep(delay)

    if unknown_jobs:
        print(f"\n> Unknown platform ({len(unknown_jobs)} jobs) - flagging as manual_review")
        for job in unknown_jobs:
            set_status(job["id"], "manual_review", "Unknown job board - apply manually")
            print(f"  [FLAG] {job['company']:<25} {job['url']}")

    print("\n" + "-" * 55)
    print("  Results:")
    for key, value in stats.items():
        if value:
            print(f"    {key:<20} {value}")

    manual_count = stats.get("manual_review", 0) + len(unknown_jobs)
    if manual_count:
        print(f"\n  [FLAG] {manual_count} jobs need manual attention.")
        print("    Run: python review_server.py -> filter by status='manual_review'")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply to approved jobs")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without actually applying")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--limit", type=int, default=MAX_APPLIES_PER_RUN, help="Max applications to submit")
    args = parser.parse_args()
    run(dry_run=args.dry_run, headless=args.headless, limit=args.limit)
