"""Apply to approved jobs, routing each one to the correct bot via ats_router."""

from __future__ import annotations

import argparse
import random
import sqlite3
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from config import AUTO_APPLY_DELAY, DB_PATH, MAX_APPLIES_PER_RUN
from indeed_apply import IndeedApplyBot
from linkedin_apply import ApplyResult, LinkedInApplyBot
from greenhouse_apply import GreenhouseApplyBot
from lever_apply import LeverApplyBot
from ats_router import ATSType, Difficulty, classify_job

Path("output").mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Routing tables
# ─────────────────────────────────────────────────────────────────────────────

# Bot class to instantiate for each ATS type (context managers).
# ATS types absent from this map have no automation support.
_BOT_CLASS: dict[ATSType, type] = {
    ATSType.LINKEDIN_EASY_APPLY: LinkedInApplyBot,
    ATSType.INDEED:              IndeedApplyBot,
    ATSType.GREENHOUSE:          GreenhouseApplyBot,
    ATSType.LEVER:               LeverApplyBot,
}

# These bots gate on an explicit login() call before applying.
_LOGIN_REQUIRED: set[ATSType] = {ATSType.LINKEDIN_EASY_APPLY, ATSType.INDEED}

_ATS_LABEL: dict[ATSType, str] = {
    ATSType.LINKEDIN_EASY_APPLY: "LinkedIn Easy Apply",
    ATSType.INDEED:              "Indeed",
    ATSType.GREENHOUSE:          "Greenhouse",
    ATSType.LEVER:               "Lever",
    ATSType.ASHBY:               "Ashby",
    ATSType.WORKDAY:             "Workday",
    ATSType.ICIMS:               "iCIMS",
    ATSType.EXTERNAL_UNKNOWN:    "External / Unknown",
}


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_approved_jobs(limit: int = 100) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, company, title, location, url, fit_score, comp_est,
               verdict, gaps, ats_type, difficulty
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


# ─────────────────────────────────────────────────────────────────────────────
# Classification
# ─────────────────────────────────────────────────────────────────────────────

def _resolve(job: dict) -> tuple[ATSType, Difficulty]:
    """
    Return (ATSType, Difficulty) for a job dict.

    Prefers values already stored in the DB (ats_type / difficulty columns).
    Falls back to classify_job(url) when the DB columns are blank.
    """
    raw_ats  = job.get("ats_type") or ""
    raw_diff = job.get("difficulty") or ""
    try:
        return ATSType(raw_ats), Difficulty(raw_diff)
    except ValueError:
        pass
    return classify_job(job.get("url", ""))


# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def _extract_external_url(result: ApplyResult) -> str:
    """Parse 'external_apply_url:...' from manual_questions or error_message."""
    sources = result.manual_questions + ([result.error_message] if result.error_message else [])
    for text in sources:
        if "external_apply_url:" in text:
            url = text.split("external_apply_url:")[-1].strip().split("|")[0].strip()
            if url:
                return url
    return ""


def _log(job: dict, result: ApplyResult) -> None:
    icon = {
        "applied":        "[OK]  ",
        "already_applied":"[SKIP]",
        "manual_review":  "[FLAG]",
        "error":          "[X]   ",
    }.get(result.status, "[?]   ")
    print(
        f"  {icon} [{job['fit_score']:>3.0f}] "
        f"{job['company']:<25} {job['title'][:35]:<35} "
        f"-> {result.status}"
    )
    for q in result.manual_questions[:3]:
        print(f"         Manual: {q[:80]}")
    if result.error_message:
        print(f"         Error:  {result.error_message[:120]}")


# ─────────────────────────────────────────────────────────────────────────────
# Per-job result handler
# ─────────────────────────────────────────────────────────────────────────────

def _commit(job: dict, result: ApplyResult) -> None:
    """Persist the ApplyResult back to the DB."""
    if result.status in ("applied", "already_applied"):
        set_status(job["id"], "applied")
    elif result.status == "manual_review":
        notes = " | ".join(result.manual_questions[:5])
        set_status(job["id"], "manual_review", notes)
    else:
        set_status(job["id"], "error", result.error_message)


# ─────────────────────────────────────────────────────────────────────────────
# Bot runner
# ─────────────────────────────────────────────────────────────────────────────

def _run_group(
    ats_type: ATSType,
    jobs: list[dict],
    headless: bool,
    dry_run: bool,
    ats_stats: dict[ATSType, dict[str, int]],
) -> None:
    """
    Run all jobs for a single ATS type through its bot.

    Updates ats_stats in-place.
    """
    if not jobs:
        return

    label = _ATS_LABEL.get(ats_type, ats_type.value)
    bot_cls = _BOT_CLASS.get(ats_type)

    if bot_cls is None:
        # No bot for this ATS type — should have been filtered out before here,
        # but guard defensively.
        return

    print(f"\n> {label} [{Difficulty.HYBRID.value if ats_type in {ATSType.GREENHOUSE, ATSType.LEVER, ATSType.ASHBY} else Difficulty.AUTO.value}] ({len(jobs)} jobs)")

    with bot_cls(headless=headless) as bot:
        if ats_type in _LOGIN_REQUIRED:
            if not bot.login():
                print(f"  [X] {label} login failed — skipping all {len(jobs)} jobs")
                for job in jobs:
                    ats_stats[ats_type]["error"] += 1
                    set_status(job["id"], "error", f"{label} login failed")
                return

        for job in jobs:
            if dry_run:
                print(f"  [DRY] {job['company']:<25} {job['title'][:40]}")
                continue

            result = bot.apply(
                job_url=job["url"],
                company=job["company"],
                title=job["title"],
            )

            # If LinkedIn returned manual_review due to an external apply URL,
            # check if that URL belongs to a Greenhouse/Lever board and re-queue.
            if result.status == "manual_review" and ats_type == ATSType.LINKEDIN_EASY_APPLY:
                ext_url = _extract_external_url(result)
                if ext_url:
                    ext_ats, _ = classify_job(ext_url)
                    if ext_ats in (ATSType.GREENHOUSE, ATSType.LEVER) and ext_ats in _BOT_CLASS:
                        # Update DB: point job at the real ATS URL and reset to approved
                        conn = sqlite3.connect(DB_PATH)
                        conn.execute(
                            "UPDATE jobs SET ats_type=?, url=?, status='approved' WHERE id=?",
                            (ext_ats.value, ext_url, job["id"]),
                        )
                        conn.commit()
                        conn.close()
                        print(f"         Reclassified as {ext_ats.value} ({ext_url[:60]}) — re-queued for next run")
                        ats_stats[ats_type]["manual_review"] += 1
                        delay = random.uniform(*AUTO_APPLY_DELAY)
                        print(f"         (waiting {delay:.1f}s)")
                        time.sleep(delay)
                        continue

            _log(job, result)
            _commit(job, result)
            ats_stats[ats_type][result.status] += 1

            delay = random.uniform(*AUTO_APPLY_DELAY)
            print(f"         (waiting {delay:.1f}s)")
            time.sleep(delay)


# ─────────────────────────────────────────────────────────────────────────────
# Summary printer
# ─────────────────────────────────────────────────────────────────────────────

def _print_summary(
    ats_stats: dict[ATSType, dict[str, int]],
    manual_jobs: dict[ATSType, list[dict]],
) -> None:
    all_statuses = ["applied", "already_applied", "manual_review", "error"]

    # Aggregate totals
    totals: dict[str, int] = defaultdict(int)
    for counts in ats_stats.values():
        for status, n in counts.items():
            totals[status] += n
    for jobs in manual_jobs.values():
        totals["manual_review"] += len(jobs)

    print("\n" + "=" * 70)
    print("  RESULTS BY ATS PLATFORM")
    print("=" * 70)

    # Header
    col_w = 10
    header = f"  {'Platform':<24}"
    for s in all_statuses:
        header += f"  {s[:col_w]:>{col_w}}"
    header += f"  {'total':>{col_w}}"
    print(header)
    print("  " + "-" * 68)

    # Rows for bots that actually ran
    for ats_type, counts in ats_stats.items():
        if not any(counts.values()):
            continue
        label = _ATS_LABEL.get(ats_type, ats_type.value)
        row = f"  {label:<24}"
        for s in all_statuses:
            n = counts.get(s, 0)
            row += f"  {(str(n) if n else '-'):>{col_w}}"
        row += f"  {sum(counts.values()):>{col_w}}"
        print(row)

    # Rows for MANUAL-flagged platforms (no bot ran)
    for ats_type, jobs in manual_jobs.items():
        if not jobs:
            continue
        label = _ATS_LABEL.get(ats_type, ats_type.value)
        row = f"  {label:<24}"
        for s in all_statuses:
            n = len(jobs) if s == "manual_review" else 0
            row += f"  {(str(n) if n else '-'):>{col_w}}"
        row += f"  {len(jobs):>{col_w}}"
        print(row)

    # Totals row
    print("  " + "-" * 68)
    row = f"  {'TOTAL':<24}"
    grand = 0
    for s in all_statuses:
        n = totals.get(s, 0)
        row += f"  {(str(n) if n else '-'):>{col_w}}"
        grand += n
    row += f"  {grand:>{col_w}}"
    print(row)

    # Flag line
    flagged = totals.get("manual_review", 0)
    if flagged:
        print(f"\n  [FLAG] {flagged} jobs need manual attention.")
        print("         Run: python review_server.py -> filter status='manual_review'")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, headless: bool = True, limit: int = MAX_APPLIES_PER_RUN) -> None:
    jobs = get_approved_jobs(limit=limit)
    if not jobs:
        print("No approved jobs found. Run the review server first (python review_server.py).")
        return

    # ── Classify every job ───────────────────────────────────────────────────
    # auto_groups:   ATSType → jobs with a working bot  (AUTO or HYBRID with bot)
    # manual_groups: ATSType → jobs with no bot or MANUAL difficulty
    auto_groups:   dict[ATSType, list[dict]] = defaultdict(list)
    manual_groups: dict[ATSType, list[dict]] = defaultdict(list)

    for job in jobs:
        ats_type, difficulty = _resolve(job)
        job["_ats_type"]   = ats_type    # annotate for downstream use
        job["_difficulty"] = difficulty

        if difficulty == Difficulty.MANUAL or ats_type not in _BOT_CLASS:
            manual_groups[ats_type].append(job)
        else:
            auto_groups[ats_type].append(job)

    # ── Print header ─────────────────────────────────────────────────────────
    auto_count   = sum(len(v) for v in auto_groups.values())
    manual_count = sum(len(v) for v in manual_groups.values())

    print("\n" + "=" * 55)
    print(f"  AUTO-APPLY  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 55)
    print(f"  Approved: {len(jobs)} jobs  (automatable: {auto_count}, manual: {manual_count})")
    if dry_run:
        print("  DRY RUN — no applications will be submitted\n")

    # ── Stamp MANUAL jobs immediately ────────────────────────────────────────
    if manual_groups:
        print("\n> MANUAL / unsupported platforms — flagging without attempting")
        for ats_type, group in manual_groups.items():
            label = _ATS_LABEL.get(ats_type, ats_type.value)
            for job in group:
                reason = f"{label} requires manual application (difficulty={job['_difficulty'].value})"
                print(f"  [FLAG] {job['company']:<25} {job['title'][:40]}")
                if not dry_run:
                    set_status(job["id"], "manual_review", reason)

    # ── Run bots for AUTO / HYBRID groups ───────────────────────────────────
    # Track per-ATS result counts for the summary table.
    ats_stats: dict[ATSType, dict[str, int]] = {
        t: defaultdict(int) for t in auto_groups
    }

    for ats_type, group in auto_groups.items():
        _run_group(ats_type, group, headless, dry_run, ats_stats)

    # ── Print summary table ──────────────────────────────────────────────────
    _print_summary(ats_stats, manual_groups)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply to approved jobs")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without submitting")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--limit", type=int, default=MAX_APPLIES_PER_RUN,
                        help="Max applications to submit")
    args = parser.parse_args()
    run(dry_run=args.dry_run, headless=args.headless, limit=args.limit)
