"""Filtering stage for scraped jobs."""

from __future__ import annotations

import hashlib
import re

import pandas as pd

from config import BLACKLIST_COMPANIES, BLACKLIST_KEYWORDS, FILTERED_CSV, RAW_CSV
from logger import get_logger
from tracker import is_seen

log = get_logger(__name__)


def make_id(company: str, title: str, location: str) -> str:
    raw = f"{company}{title}{location}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_blacklisted_company(company_raw: str) -> tuple[bool, str]:
    company_norm = _normalise(company_raw)
    for term in BLACKLIST_COMPANIES:
        term_norm = _normalise(term)
        pattern = r"(?<!\w)" + re.escape(term_norm) + r"(?!\w)"
        if re.search(pattern, company_norm):
            log.debug("Company %r matched blacklist term %r", company_raw, term)
            return True, f"blacklisted company: {term}"
    return False, ""


def _is_blacklisted_keyword(row: dict) -> tuple[bool, str]:
    title = _normalise(str(row.get("title", "")))
    desc = _normalise(str(row.get("description", "")))
    for keyword in BLACKLIST_KEYWORDS:
        keyword_norm = _normalise(keyword)
        if keyword_norm in title or keyword_norm in desc:
            return True, f"blacklisted keyword: {keyword}"
    return False, ""


def _hard_reject_by_structure(row: dict, title_norm: str) -> tuple[bool, str]:
    senior_patterns = [
        r"\bsr\b staff",
        r"\bstaff engineer\b",
        r"\bprincipal\b",
        r"\bsenior staff\b",
        r"\bdistinguished\b",
        r"\bdirector\b",
        r"\bvp of\b",
        r"\bhead of\b",
        r"\bvice president\b",
        r"\bprincipal architect\b",
    ]
    for pattern in senior_patterns:
        if re.search(pattern, title_norm):
            return True, f"seniority: {pattern}"

    desc_norm = _normalise(str(row.get("description", "")))
    internship_signals = [
        "unpaid",
        "stipend",
        "first month is unpaid",
        "internship programme",
        "trainee programme",
    ]
    if "intern" in title_norm and "senior" not in title_norm:
        return True, "role type: internship"
    if any(signal in desc_norm for signal in internship_signals):
        return True, "role type: unpaid/stipend"

    exp_matches = re.findall(r"(\d+)\s*\+?\s*years?\s*(?:of\s*)?(?:experience|exp)", desc_norm)
    if exp_matches:
        min_exp = min(int(match) for match in exp_matches)
        if min_exp >= 5:
            return True, f"experience floor: {min_exp}+ yrs"

    return False, ""


def run() -> pd.DataFrame:
    log.info("=== FILTER START ===")

    df = pd.read_csv(RAW_CSV)
    df.columns = [column.lower().replace(" ", "_") for column in df.columns]
    log.info("Loaded %d raw jobs from %s", len(df), RAW_CSV)

    kept: list[pd.Series] = []
    reasons: dict[str, int] = {
        "blacklisted_company": 0,
        "blacklisted_keyword": 0,
        "already_seen": 0,
        "hard_reject": 0,
    }

    for _, row in df.iterrows():
        company = str(row.get("company", ""))
        title = str(row.get("title", ""))
        location = str(row.get("location", ""))
        job_id = make_id(company, title, location)

        if is_seen(job_id):
            reasons["already_seen"] += 1
            continue

        blacklisted_company, company_reason = _is_blacklisted_company(company)
        if blacklisted_company:
            reasons["blacklisted_company"] += 1
            log.debug("Filtered [%s]: %s / %s", company_reason, company, title)
            continue

        blacklisted_keyword, keyword_reason = _is_blacklisted_keyword(row)
        if blacklisted_keyword:
            reasons["blacklisted_keyword"] += 1
            log.debug("Filtered [%s]: %s / %s", keyword_reason, company, title)
            continue

        hard_reject, hard_reason = _hard_reject_by_structure(row, _normalise(title))
        if hard_reject:
            reasons["hard_reject"] += 1
            log.debug("Hard reject [%s]: %s / %s", hard_reason, company, title)
            continue

        row_copy = row.copy()
        row_copy["id"] = job_id
        kept.append(row_copy)

    result = pd.DataFrame(kept)
    result.to_csv(FILTERED_CSV, index=False)

    log.info(
        "Filter complete - kept: %d | blacklisted company: %d | blacklisted keyword: %d | already seen: %d | hard reject: %d",
        len(result),
        reasons["blacklisted_company"],
        reasons["blacklisted_keyword"],
        reasons["already_seen"],
        reasons["hard_reject"],
    )

    if not result.empty:
        for term in BLACKLIST_COMPANIES:
            term_norm = _normalise(term)
            surviving = result[result["company"].apply(lambda value: term_norm in _normalise(str(value)))]
            if not surviving.empty:
                log.warning(
                    "Blacklist term '%s' still present in %d kept jobs - check normalisation: %s",
                    term,
                    len(surviving),
                    surviving["company"].tolist()[:5],
                )

    log.info("=== FILTER DONE ===")
    return result
