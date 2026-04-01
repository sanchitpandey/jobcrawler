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


def _verify_linkedin_easy_apply(jobs: pd.DataFrame) -> pd.DataFrame:
    if jobs.empty or "site" not in jobs.columns or "job_url" not in jobs.columns:
        return jobs

    linkedin_mask = jobs["site"].astype(str).str.lower() == "linkedin"
    linkedin_jobs = jobs[linkedin_mask].copy()
    if linkedin_jobs.empty:
        return jobs

    from linkedin_apply import LinkedInApplyBot

    print(f"  Verifying LinkedIn Easy Apply on {len(linkedin_jobs)} jobs...")
    keep_indices: list[int] = []
    rejected = 0

    with LinkedInApplyBot(headless=True) as bot:
        if not bot.login():
            raise RuntimeError("LinkedIn Easy Apply verification requires a valid LinkedIn session.")

        for checked, (idx, row) in enumerate(linkedin_jobs.iterrows(), start=1):
            company = str(row.get("company", "") or "")
            title = str(row.get("title", "") or "")
            job_url = str(row.get("job_url", "") or "")

            is_easy_apply, reason = bot.has_easy_apply(job_url, company=company, title=title)
            if is_easy_apply:
                keep_indices.append(idx)
            else:
                rejected += 1
                print(f"    -> rejected: {company} | {title} | {reason}")

            if checked % 10 == 0 or checked == len(linkedin_jobs):
                print(f"    progress: {checked}/{len(linkedin_jobs)} checked, {rejected} rejected")

    keep_mask = ~linkedin_mask
    keep_mask.loc[keep_indices] = True
    verified = jobs[keep_mask].reset_index(drop=True)
    print(f"  LinkedIn Easy Apply verification kept {len(keep_indices)}/{len(linkedin_jobs)} jobs")
    return verified


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
            easy_apply=True,
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
    combined = _verify_linkedin_easy_apply(combined)

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
