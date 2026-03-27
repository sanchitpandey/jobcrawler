"""Scrape jobs from supported job boards using JobSpy."""

from __future__ import annotations

import random
import time

import pandas as pd
from jobspy import scrape_jobs

from config import HOURS_OLD, LOCATION, RAW_CSV, RESULTS_PER_QUERY, SEARCH_TERMS, SITES

CITY_QUERIES = [
    ("AI ML Engineer", "Bengaluru"),
    ("Machine Learning Engineer", "Hyderabad"),
    ("AI Engineer", "Pune"),
]


_site_failures: dict[str, int] = {}

_SITE_FAILURE_LIMIT = 3


def _scrape_term(term: str, location: str, sites: list[str]) -> pd.DataFrame | None:
    active_sites = [s for s in sites if _site_failures.get(s, 0) < _SITE_FAILURE_LIMIT]
    if not active_sites:
        print(f"  Skipping '{term}' in '{location}' — all sites disabled")
        return pd.DataFrame()

    print(f"  Searching: '{term}' in '{location}'...")
    try:
        jobs = scrape_jobs(
            site_name=active_sites,
            search_term=term,
            location=location,
            results_wanted=RESULTS_PER_QUERY,
            hours_old=HOURS_OLD,
            job_type="fulltime",
            linkedin_fetch_description=True,
        )
        print(f"    -> {len(jobs)} results")
        return jobs
    except Exception as exc:
        print(f"    -> Error: {exc}")
        for site in active_sites:
            _site_failures[site] = _site_failures.get(site, 0) + 1
            if _site_failures[site] >= _SITE_FAILURE_LIMIT:
                print(f"    !! {site} hit {_SITE_FAILURE_LIMIT} consecutive failures — disabling for this run")
        return None


def run() -> pd.DataFrame:
    all_jobs: list[pd.DataFrame] = []
    queries_run = 0
    query_errors = 0

    all_queries: list[tuple[str, str, list[str]]] = (
        [(term, LOCATION, SITES) for term in SEARCH_TERMS]
        + [(term, city, ["linkedin"]) for term, city in CITY_QUERIES]
    )

    for i, (term, location, sites) in enumerate(all_queries):
        result = _scrape_term(term, location, sites)
        queries_run += 1
        if result is None:
            query_errors += 1
        else:
            all_jobs.append(result)

        if i < len(all_queries) - 1:
            delay = random.uniform(3, 8)
            print(f"    (waiting {delay:.1f}s before next query)")
            time.sleep(delay)

    combined = pd.concat(all_jobs, ignore_index=True)
    combined = combined.dropna(subset=["title", "company"])

    total_before_dedup = len(combined)

    # Normalize company names to catch "Google" vs "Google LLC" vs "Google India"
    combined["_company_norm"] = combined["company"].str.lower().str.strip()
    combined["_company_norm"] = combined["_company_norm"].str.replace(
        r"\s*(llc|inc|ltd|pvt|private|limited|corp|corporation|india|global)\s*\.?\s*",
        " ", regex=True
    ).str.strip()
    combined = combined.drop_duplicates(subset=["title", "_company_norm"])
    combined = combined.drop(columns=["_company_norm"])

    combined = combined.drop_duplicates(subset=["title", "company", "location"])
    combined = combined.drop_duplicates(subset=["job_url"])
    combined = combined.drop_duplicates(subset=["title", "company"])

    combined.to_csv(RAW_CSV, index=False)

    print(f"\n  Scrape summary:")
    print(f"    Total raw results: {total_before_dedup}")
    print(f"    After dedup: {len(combined)}")
    print(f"    By source: {combined['site'].value_counts().to_dict()}")
    print(f"    Queries run: {queries_run}")
    print(f"    Query errors: {query_errors}")

    return combined


if __name__ == "__main__":
    run()
