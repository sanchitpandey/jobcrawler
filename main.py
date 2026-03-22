"""
main.py  —  pipeline orchestrator with full logging
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from logger import get_logger
log = get_logger(__name__)

from providers import get_session
session = get_session()

# Import pipeline stages (logging kicks in the moment these modules load)
from tracker import init_db, upsert_job, print_dashboard
import scrape
import filter as f
import score
import cover
import pandas as pd
from config import SCORED_CSV, DB_PATH


def run_pipeline(skip_scrape: bool = False, cover_n: int = 5, limit: int | None = None):
    start_time = datetime.now()
    log.info("=" * 60)
    log.info("JOB CRAWLER PIPELINE START  —  %s", start_time.strftime("%Y-%m-%d %H:%M"))
    log.info("Options: skip_scrape=%s  cover_n=%d  limit=%s",
             skip_scrape, cover_n, limit)
    log.info("Log file: output/pipeline.log")
    log.info("=" * 60)

    Path("output").mkdir(exist_ok=True)
    init_db()
    log.info("Tracker DB initialised at %s", DB_PATH)

    # ── Step 1: Scrape ─────────────────────────────────────────────────────
    log.info("STEP 1 — Scraping")
    if skip_scrape:
        log.info("Skipping scrape (--no-scrape flag set)")
    else:
        try:
            scrape.run()
            log.info("Scrape complete")
        except Exception as e:
            log.error("Scrape FAILED: %s", e, exc_info=True)
            log.error("Aborting pipeline — check output/pipeline.log for details")
            sys.exit(1)

    # ── Step 2: Filter ────────────────────────────────────────────────────
    log.info("STEP 2 — Filtering")
    try:
        filtered_df = f.run()
        log.info("Filter complete — %d jobs kept", len(filtered_df))
    except Exception as e:
        log.error("Filter FAILED: %s", e, exc_info=True)
        sys.exit(1)

    if filtered_df.empty:
        log.warning("No jobs survived filtering — nothing to score or apply to.")
        return

    if limit:
        log.info("DEBUG LIMIT — capping to %d jobs", limit)
        filtered_df = filtered_df.head(limit)
        filtered_df.to_csv("output/jobs_filtered.csv", index=False)

    # ── Step 3: Score ─────────────────────────────────────────────────────
    
    log.info("STEP 3 — Scoring with %s (%s)", session.provider.name, session.current_model)
    try:
        scored_df = score.run()
        log.info("Scoring complete — %d rows in scored CSV", len(scored_df))
    except EnvironmentError as e:
        # Missing GROQ_API_KEY — give a clear actionable message
        log.error("Environment error: %s", e)
        log.error("Fix: set the GROQ_API_KEY environment variable and re-run.")
        sys.exit(1)
    except Exception as e:
        log.error("Scoring FAILED: %s", e, exc_info=True)
        sys.exit(1)

    # ── Step 4: Save to tracker DB ────────────────────────────────────────
    log.info("STEP 4 — Saving to tracker DB")
    saved, skipped = 0, 0
    now = datetime.now().isoformat()

    for _, row in scored_df.iterrows():
        fit_score = row.get("fit_score")
        if pd.isna(fit_score):
            skipped += 1
            continue

        company  = row.get("company")
        title    = row.get("title")
        location = row.get("location")

        def _str(v):
            return str(v.iloc[0]) if isinstance(v, pd.Series) else str(v)

        try:
            upsert_job({
                "id":          str(row.get("id", "")),
                "company":     _str(company),
                "title":       _str(title),
                "location":    _str(location),
                "url":         str(row.get("job_url", row.get("url", ""))),
                "fit_score":   float(fit_score),
                "comp_est":    str(row.get("comp_estimate", "")),
                "verdict":     str(row.get("verdict", "")),
                "gaps":        str(row.get("gaps", "")),
                "status":      "new",
                "cover_letter":"",
                "scraped_at":  now,
            })
            saved += 1
        except Exception as e:
            log.warning("DB upsert failed for %s / %s: %s",
                        company, title, e)
            skipped += 1

    log.info("DB update — %d jobs saved, %d skipped (no score)", saved, skipped)

    # ── Step 5: Cover letters ─────────────────────────────────────────────
    log.info("STEP 5 — Generating up to %d cover letters", cover_n)
    try:
        generated = cover.run(top_n=cover_n)
        log.info("Cover letters — %d generated", len(generated))
    except Exception as e:
        log.error("Cover letter generation FAILED: %s", e, exc_info=True)
        log.info("(Non-fatal — pipeline continues)")

    # ── Done ──────────────────────────────────────────────────────────────
    elapsed = (datetime.now() - start_time).seconds
    log.info("=" * 60)
    log.info("PIPELINE COMPLETE — total time: %dm %ds",
             elapsed // 60, elapsed % 60)
    log.info("Next step: python review_server.py  →  approve jobs  →  python apply.py")
    log.info("Full log:  output/pipeline.log")
    log.info("=" * 60)

    print_dashboard()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Job crawler pipeline")
    parser.add_argument("--no-scrape", action="store_true",
                        help="Skip scraping; re-score existing raw CSV")
    parser.add_argument("--covers",    type=int, default=5,
                        help="Number of cover letters to generate")
    parser.add_argument("--dashboard", action="store_true",
                        help="Just show dashboard, skip pipeline")
    parser.add_argument("--limit",     type=int, default=None,
                        help="Limit jobs processed (debug)")
    parser.add_argument("--debug",     action="store_true",
                        help="Set console log level to DEBUG")
    args = parser.parse_args()

    if args.debug:
        import logging
        logging.getLogger("crawler").setLevel(logging.DEBUG)
        # Also set the console handler to DEBUG
        import logger as _lg
        _lg._setup()
        for h in logging.getLogger().handlers:
            if hasattr(h, "stream"):   # StreamHandler (console)
                h.setLevel(logging.DEBUG)

    if args.dashboard:
        init_db()
        print_dashboard()
    else:
        run_pipeline(
            skip_scrape = args.no_scrape,
            cover_n     = args.covers,
            limit       = args.limit,
        )