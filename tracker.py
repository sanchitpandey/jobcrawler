# tracker.py
import sqlite3
from config import DB_PATH

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id          TEXT PRIMARY KEY,  -- hash of company+title+location
            company     TEXT,
            title       TEXT,
            location    TEXT,
            url         TEXT,
            fit_score   REAL,
            comp_est    TEXT,
            verdict     TEXT,
            gaps        TEXT,
            status      TEXT DEFAULT 'new',  -- new/reviewed/applied/interview/rejected
            cover_letter TEXT,
            scraped_at  TEXT,
            applied_at  TEXT
        )
    """)
    conn.commit()
    conn.close()

def is_seen(job_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    return row is not None

def upsert_job(job: dict):
    conn = sqlite3.connect(DB_PATH)
    # Insert only if not already present
    conn.execute("""
        INSERT OR IGNORE INTO jobs 
        (id, company, title, location, url, fit_score, comp_est, 
         verdict, gaps, status, cover_letter, scraped_at)
        VALUES (:id,:company,:title,:location,:url,:fit_score,
                :comp_est,:verdict,:gaps,:status,:cover_letter,:scraped_at)
    """, job)
    # Update scoring fields without touching status/applied_at
    conn.execute("""
        UPDATE jobs SET
            fit_score  = :fit_score,
            comp_est   = :comp_est,
            verdict    = :verdict,
            gaps       = :gaps,
            scraped_at = :scraped_at
        WHERE id = :id AND status = 'new'
    """, job)
    conn.commit()
    conn.close()

def mark_applied(job_id, timestamp):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE jobs SET status='applied', applied_at=? WHERE id=?",
        (timestamp, job_id)
    )
    conn.commit()
    conn.close()

def get_shortlist(min_score=65, limit=20):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("""
        SELECT company, title, location, url, fit_score, comp_est, 
               verdict, gaps, cover_letter
        FROM jobs 
        WHERE fit_score >= ? AND status = 'new'
        ORDER BY fit_score DESC 
        LIMIT ?
    """, (min_score, limit)).fetchall()
    conn.close()
    return rows

def print_dashboard():
    conn = sqlite3.connect(DB_PATH)
    print("\n━━━ JOB TRACKER DASHBOARD ━━━")
    for status in ['new', 'applied', 'interview', 'rejected']:
        count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status=?", (status,)
        ).fetchone()[0]
        print(f"  {status:<12} {count}")
    print()
    print("Top 10 unreviewed (by fit score):")
    rows = conn.execute("""
        SELECT company, title, fit_score, comp_est, url
        FROM jobs WHERE status='new' AND fit_score IS NOT NULL
        ORDER BY fit_score DESC LIMIT 10
    """).fetchall()
    for i, r in enumerate(rows, 1):
        print(f"  {i:>2}. [{r[2]:>3.0f}%] {r[0]:<25} {r[1]:<35} {r[3] or '?'}")
        print(f"      {r[4]}")
    conn.close()

def approve_jobs(job_ids: list[str]):
    """Mark jobs as approved (ready for auto-apply)."""
    conn = sqlite3.connect(DB_PATH)
    placeholders = ",".join("?" * len(job_ids))
    conn.execute(
        f"UPDATE jobs SET status='approved' WHERE id IN ({placeholders})",
        job_ids
    )
    conn.commit()
    conn.close()


def mark_manual_review(job_id: str, reason: str = ""):
    """Mark a job as needing manual application."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "UPDATE jobs SET status='manual_review', gaps=? WHERE id=?",
        (reason, job_id)
    )
    conn.commit()
    conn.close()


def get_manual_review_jobs(limit: int = 50) -> list[dict]:
    """Return jobs that need manual attention."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, company, title, location, url, fit_score, comp_est, gaps
        FROM   jobs
        WHERE  status = 'manual_review'
        ORDER  BY fit_score DESC
        LIMIT  ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def print_apply_summary():
    """Print a summary of the apply pipeline status."""
    conn = sqlite3.connect(DB_PATH)
    print("\n━━━ APPLY PIPELINE SUMMARY ━━━")
    statuses = [
        ("new",           "Scored, awaiting review"),
        ("approved",      "Approved, queued for apply"),
        ("applied",       "Application submitted"),
        ("manual_review", "Needs manual application"),
        ("skipped",       "Skipped by user"),
        ("interview",     "Interview stage"),
        ("rejected",      "Rejected"),
        ("error",         "Apply error"),
    ]
    for status, label in statuses:
        count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status=?", (status,)
        ).fetchone()[0]
        if count > 0:
            print(f"  {label:<30} {count:>4}")
    print()

    # Show manual review jobs
    manual = conn.execute("""
        SELECT company, title, url, gaps
        FROM   jobs WHERE status='manual_review'
        ORDER  BY fit_score DESC LIMIT 10
    """).fetchall()
    if manual:
        print("Manual review required:")
        for r in manual:
            print(f"  • {r[0]:<25} {r[1][:40]}")
            print(f"    Reason: {str(r[3])[:80]}")
            print(f"    URL: {r[2]}")
        print()
    conn.close()