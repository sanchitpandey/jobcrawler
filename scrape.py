"""Scrape jobs from supported job boards using JobSpy."""

from __future__ import annotations

import pandas as pd
from jobspy import scrape_jobs

from config import HOURS_OLD, LOCATION, RAW_CSV, RESULTS_PER_QUERY, SEARCH_TERMS, SITES


def run() -> pd.DataFrame:
    all_jobs: list[pd.DataFrame] = []
    for term in SEARCH_TERMS:
        print(f"  Searching: '{term}'...")
        try:
            jobs = scrape_jobs(
                site_name=SITES,
                search_term=term,
                location=LOCATION,
                results_wanted=RESULTS_PER_QUERY,
                hours_old=HOURS_OLD,
                job_type="fulltime",
                linkedin_fetch_description=True,
            )
            all_jobs.append(jobs)
            print(f"    -> {len(jobs)} results")
        except Exception as exc:
            print(f"    -> Error: {exc}")

    combined = pd.concat(all_jobs, ignore_index=True)
    combined = combined.dropna(subset=["title", "company"])
    combined = combined.drop_duplicates(subset=["title", "company", "location"])
    combined = combined.drop_duplicates(subset=["job_url"])
    combined = combined.drop_duplicates(subset=["title", "company"])
    combined.to_csv(RAW_CSV, index=False)
    print(f"  Total unique: {len(combined)} -> {RAW_CSV}")
    return combined


if __name__ == "__main__":
    run()
