"""Filtering logic for scraped jobs — ported from legacy/filter.py.

All pandas/CSV I/O and config imports removed. Callers pass blacklists directly.

Public API
----------
make_id(company, title, location) → str
filter_job(job, blacklist_companies, blacklist_keywords) → tuple[bool, str]
    Returns (should_keep, reject_reason). reject_reason is "" when kept.
"""

from __future__ import annotations

import hashlib
import logging
import re

log = logging.getLogger("crawler.filter")


def make_id(company: str, title: str, location: str) -> str:
    raw = f"{company}{title}{location}".lower().strip()
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_blacklisted_company(company_raw: str, blacklist_companies: list[str]) -> tuple[bool, str]:
    company_norm = _normalise(company_raw)
    for term in blacklist_companies:
        term_norm = _normalise(term)
        pattern = r"(?<!\w)" + re.escape(term_norm) + r"(?!\w)"
        if re.search(pattern, company_norm):
            log.debug("Company %r matched blacklist term %r", company_raw, term)
            return True, f"blacklisted company: {term}"
    return False, ""


def _is_blacklisted_keyword(job: dict, blacklist_keywords: list[str]) -> tuple[bool, str]:
    title = _normalise(str(job.get("title", "")))
    desc = _normalise(str(job.get("description", "")))
    for keyword in blacklist_keywords:
        keyword_norm = _normalise(keyword)
        if keyword_norm in title or keyword_norm in desc:
            return True, f"blacklisted keyword: {keyword}"
    return False, ""


def _hard_reject_by_structure(job: dict, title_norm: str) -> tuple[bool, str]:
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

    desc_norm = _normalise(str(job.get("description", "")))
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


def filter_job(
    job: dict,
    blacklist_companies: list[str],
    blacklist_keywords: list[str],
) -> tuple[bool, str]:
    """Decide whether a job should be kept or rejected.

    Parameters
    ----------
    job:
        Dict with at minimum ``title``, ``company``, ``description`` keys.
    blacklist_companies:
        List of company name substrings to reject (from Profile.blacklist_companies).
    blacklist_keywords:
        List of title/description keywords to reject (from Profile.blacklist_keywords).

    Returns
    -------
    ``(should_keep, reject_reason)`` — ``reject_reason`` is ``""`` when kept.
    """
    company = str(job.get("company", ""))
    title = str(job.get("title", ""))
    title_norm = _normalise(title)

    hit, reason = _is_blacklisted_company(company, blacklist_companies)
    if hit:
        return False, reason

    hit, reason = _is_blacklisted_keyword(job, blacklist_keywords)
    if hit:
        return False, reason

    hit, reason = _hard_reject_by_structure(job, title_norm)
    if hit:
        return False, reason

    return True, ""
