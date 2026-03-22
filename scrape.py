# scrape.py
from jobspy import scrape_jobs
from config import SEARCH_TERMS, LOCATION, RESULTS_PER_QUERY, HOURS_OLD, SITES, RAW_CSV
import pandas as pd

def run():
    all_jobs = []
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
            print(f"    → {len(jobs)} results")
        except Exception as e:
            print(f"    → Error: {e}")

    combined = pd.concat(all_jobs, ignore_index=True)
    combined = combined.dropna(subset=["title", "company"])
    combined = combined.drop_duplicates(subset=["title", "company", "location"])
    combined = combined.drop_duplicates(subset=["job_url"])
    combined = combined.drop_duplicates(subset=["title", "company"])
    combined.to_csv(RAW_CSV, index=False)
    print(f"  Total unique: {len(combined)} → {RAW_CSV}")
    return combined

if __name__ == "__main__":
    run()