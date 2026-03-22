"""
filter.py — fixed blacklist matching
─────────────────────────────────────
Bug fixed: original used `term in company.lower()` which fails when company
names have extra words, spacing variants, or punctuation differences.
e.g. "lmj innovations" did not match "LMJ Innovations" because the raw
company string from LinkedIn sometimes has extra characters.

Fix: normalise both sides (strip punctuation, collapse whitespace) before
comparing. Also added token-level matching so "uplers" catches
"Uplers India", "Uplers Pvt Ltd", etc.
"""

import re
import hashlib
import pandas as pd
from logger import get_logger
from config import (
    RAW_CSV, FILTERED_CSV,
    BLACKLIST_COMPANIES, BLACKLIST_KEYWORDS, MIN_COMP_LPA
)
from tracker import is_seen

log = get_logger(__name__)


def make_id(company: str, title: str, location: str) -> str:
    s = f"{company}{title}{location}".lower().strip()
    return hashlib.md5(s.encode()).hexdigest()[:12]


def _normalise(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)   # remove punctuation
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_blacklisted_company(company_raw: str) -> tuple[bool, str]:
    """
    Check company name against blacklist with fuzzy matching.
    A blacklist term matches if it appears as a token-boundary substring
    in the normalised company name.
    """
    company_norm = _normalise(company_raw)
    for term in BLACKLIST_COMPANIES:
        term_norm = _normalise(term)
        # Token-boundary match: term must be a complete word/phrase, not a fragment
        # e.g. "recro" should not match "recruiter" but will match "Recro Pvt Ltd"
        pattern = r"(?<!\w)" + re.escape(term_norm) + r"(?!\w)"
        if re.search(pattern, company_norm):
            log.debug("Company %r matched blacklist term %r", company_raw, term)
            return True, f"blacklisted company: {term}"
    return False, ""


def _is_blacklisted_keyword(row: dict) -> tuple[bool, str]:
    title = _normalise(str(row.get("title", "")))
    desc  = _normalise(str(row.get("description", "")))
    for kw in BLACKLIST_KEYWORDS:
        kw_norm = _normalise(kw)
        if kw_norm in title or kw_norm in desc:
            return True, f"blacklisted keyword: {kw}"
    return False, ""

def _hard_reject_by_structure(row: dict, title: str) -> tuple[bool, str]:
    """
    Deterministic rejections that don't need LLM judgment.
    title is already _normalised().
    """
    # 1. Seniority — these interviews are unpassable for a fresher
    SENIOR_TITLE_PATTERNS = [
        r"\bsr\b staff", r"\bstaff engineer\b", r"\bprincipal\b",
        r"\bsenior staff\b", r"\bdistinguished\b", r"\bdirector\b",
        r"\bvp of\b", r"\bhead of\b", r"\bvice president\b",
        r"\bprincipal architect\b",                     # usually implies 8+ yrs
    ]
    for pat in SENIOR_TITLE_PATTERNS:
        if re.search(pat, title):
            return True, f"seniority: {pat}"

    # 2. Role type — internship/contract when seeking full-time
    desc_norm = _normalise(str(row.get("description", "")))
    INTERNSHIP_SIGNALS = [
        "unpaid", "stipend", "first month is unpaid",
        "internship programme", "trainee programme",
    ]
    # only reject on title-level intern, not description mentions
    if "intern" in title and "senior" not in title:
        return True, "role type: internship"
    if any(s in desc_norm for s in INTERNSHIP_SIGNALS):
        return True, "role type: unpaid/stipend"

    # 3. Minimum experience — hard cap at 6 years before wasting LLM tokens
    exp_matches = re.findall(
        r'(\d+)\s*\+?\s*years?\s*(?:of\s*)?(?:experience|exp)', desc_norm
    )
    if exp_matches:
        min_exp = min(int(x) for x in exp_matches)
        if min_exp >= 7:
            return True, f"experience floor: {min_exp}+ yrs"

    return False, ""

def run() -> pd.DataFrame:
    log.info("=== FILTER START ===")

    df = pd.read_csv(RAW_CSV)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    log.info("Loaded %d raw jobs from %s", len(df), RAW_CSV)

    kept = []
    reasons: dict[str, int] = {
        "blacklisted_company": 0,
        "blacklisted_keyword": 0,
        "already_seen": 0,
    }

    for _, row in df.iterrows():
        company  = str(row.get("company", ""))
        title    = str(row.get("title", ""))
        location = str(row.get("location", ""))
        job_id   = make_id(company, title, location)

        # Already in DB
        if is_seen(job_id):
            reasons["already_seen"] += 1
            log.debug("Already seen: %s / %s", company, title)
            continue

        # Company blacklist (fuzzy)
        bl_co, reason_co = _is_blacklisted_company(company)
        if bl_co:
            reasons["blacklisted_company"] += 1
            log.debug("Filtered [%s]: %s / %s", reason_co, company, title)
            continue

        # Keyword blacklist
        bl_kw, reason_kw = _is_blacklisted_keyword(row)
        if bl_kw:
            reasons["blacklisted_keyword"] += 1
            log.debug("Filtered [%s]: %s / %s", reason_kw, company, title)
            continue

        title_norm = _normalise(title)
        hard_out, reason_hard = _hard_reject_by_structure(row, title_norm)
        if hard_out:
            reasons.setdefault("hard_reject", 0)
            reasons["hard_reject"] += 1
            log.debug("Hard reject [%s]: %s / %s", reason_hard, company, title)
            continue

        row_copy = row.copy()
        row_copy["id"] = job_id
        kept.append(row_copy)

    result = pd.DataFrame(kept)
    result.to_csv(FILTERED_CSV, index=False)

    log.info(
        "Filter complete — kept: %d | blacklisted company: %d | "
        "blacklisted keyword: %d | already seen: %d | "
        "below min comp: %d | hard reject: %d",
        len(result),
        reasons["blacklisted_company"],
        reasons["blacklisted_keyword"],
        reasons["already_seen"],
        reasons.get("below_min_comp", 0),
        reasons.get("hard_reject", 0),
    )

    # Warn if any blacklisted company names still appear (sanity check)
    if not result.empty:
        for term in BLACKLIST_COMPANIES:
            term_norm = _normalise(term)
            surviving = result[
                result["company"].apply(lambda c: term_norm in _normalise(str(c)))
            ]
            if not surviving.empty:
                log.warning(
                    "Blacklist term '%s' still present in %d kept jobs — "
                    "check normalisation: %s",
                    term, len(surviving),
                    surviving["company"].tolist()[:5]
                )

    log.info("=== FILTER DONE ===")
    return result