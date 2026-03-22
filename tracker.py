from __future__ import annotations

import sqlite3
from datetime import datetime

from core.storage import db_connection


def init_db() -> None:
    with db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                company TEXT,
                title TEXT,
                location TEXT,
                url TEXT,
                fit_score REAL,
                comp_est TEXT,
                verdict TEXT,
                gaps TEXT,
                status TEXT DEFAULT 'new',
                cover_letter TEXT,
                scraped_at TEXT,
                applied_at TEXT
            )
            """
        )
        conn.commit()


def is_seen(job_id: str) -> bool:
    with db_connection() as conn:
        row = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row is not None


def upsert_job(job: dict) -> None:
    with db_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO jobs
            (id, company, title, location, url, fit_score, comp_est,
             verdict, gaps, status, cover_letter, scraped_at)
            VALUES (:id, :company, :title, :location, :url, :fit_score,
                    :comp_est, :verdict, :gaps, :status, :cover_letter, :scraped_at)
            """,
            job,
        )
        conn.execute(
            """
            UPDATE jobs SET
                fit_score = :fit_score,
                comp_est = :comp_est,
                verdict = :verdict,
                gaps = :gaps,
                scraped_at = :scraped_at
            WHERE id = :id AND status = 'new'
            """,
            job,
        )
        conn.commit()


def mark_applied(job_id: str, timestamp: str | None = None) -> None:
    with db_connection() as conn:
        conn.execute(
            "UPDATE jobs SET status='applied', applied_at=? WHERE id=?",
            (timestamp or datetime.now().isoformat(), job_id),
        )
        conn.commit()


def get_shortlist(min_score: int = 65, limit: int = 20):
    with db_connection() as conn:
        return conn.execute(
            """
            SELECT company, title, location, url, fit_score, comp_est, verdict, gaps, cover_letter
            FROM jobs
            WHERE fit_score >= ? AND status = 'new'
            ORDER BY fit_score DESC
            LIMIT ?
            """,
            (min_score, limit),
        ).fetchall()


def print_dashboard() -> None:
    with db_connection() as conn:
        print("\nJOB TRACKER DASHBOARD")
        for status in ["new", "applied", "interview", "rejected"]:
            count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status=?", (status,)).fetchone()[0]
            print(f"  {status:<12} {count}")
        print()
        print("Top 10 unreviewed (by fit score):")
        rows = conn.execute(
            """
            SELECT company, title, fit_score, comp_est, url
            FROM jobs
            WHERE status='new' AND fit_score IS NOT NULL
            ORDER BY fit_score DESC
            LIMIT 10
            """
        ).fetchall()
        for index, row in enumerate(rows, 1):
            print(f"  {index:>2}. [{row[2]:>3.0f}%] {row[0]:<25} {row[1]:<35} {row[3] or '?'}")
            print(f"      {row[4]}")


def approve_jobs(job_ids: list[str]) -> None:
    if not job_ids:
        return
    with db_connection() as conn:
        placeholders = ",".join("?" * len(job_ids))
        conn.execute(f"UPDATE jobs SET status='approved' WHERE id IN ({placeholders})", job_ids)
        conn.commit()


def mark_manual_review(job_id: str, reason: str = "") -> None:
    with db_connection() as conn:
        conn.execute("UPDATE jobs SET status='manual_review', gaps=? WHERE id=?", (reason, job_id))
        conn.commit()


def get_manual_review_jobs(limit: int = 50) -> list[dict]:
    with db_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, company, title, location, url, fit_score, comp_est, gaps
            FROM jobs
            WHERE status = 'manual_review'
            ORDER BY fit_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def print_apply_summary() -> None:
    with db_connection() as conn:
        print("\nAPPLY PIPELINE SUMMARY")
        statuses = [
            ("new", "Scored, awaiting review"),
            ("approved", "Approved, queued for apply"),
            ("applied", "Application submitted"),
            ("manual_review", "Needs manual application"),
            ("skipped", "Skipped by user"),
            ("interview", "Interview stage"),
            ("rejected", "Rejected"),
            ("error", "Apply error"),
        ]
        for status, label in statuses:
            count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status=?", (status,)).fetchone()[0]
            if count > 0:
                print(f"  {label:<30} {count:>4}")
        print()
