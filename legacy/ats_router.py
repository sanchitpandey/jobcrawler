"""
ats_router.py
─────────────
Classifies job postings by ATS platform and expected automation difficulty,
then resolves the appropriate apply-handler key.

Public API
----------
classify_job(url)        → tuple[ATSType, Difficulty]
route_application(job)   → str   (handler key, e.g. "linkedin", "external")
"""

from __future__ import annotations

import re
from enum import Enum
from urllib.parse import urlparse


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class ATSType(str, Enum):
    """Known ATS platforms plus a catch-all for unrecognised external links."""
    LINKEDIN_EASY_APPLY = "linkedin_easy_apply"
    GREENHOUSE          = "greenhouse"
    LEVER               = "lever"
    WORKDAY             = "workday"
    ASHBY               = "ashby"
    ICIMS               = "icims"
    INDEED              = "indeed"
    EXTERNAL_UNKNOWN    = "external_unknown"


class Difficulty(str, Enum):
    """
    Expected automation difficulty for the application flow.

    AUTO   – can be submitted end-to-end without human intervention.
    HYBRID – partially automatable; some steps may need manual handling.
    MANUAL – no reliable automation path; must be done by a human.
    """
    AUTO   = "auto"
    HYBRID = "hybrid"
    MANUAL = "manual"


# ─────────────────────────────────────────────────────────────────────────────
# URL pattern rules
# Each entry: (compiled regex matched against the full URL, ATSType, Difficulty)
# Rules are evaluated in order; the first match wins.
# ─────────────────────────────────────────────────────────────────────────────

_RULES: list[tuple[re.Pattern[str], ATSType, Difficulty]] = [
    # ── LinkedIn ──────────────────────────────────────────────────────────────
    # Easy Apply URLs stay on linkedin.com/jobs/view/…
    (re.compile(r"linkedin\.com/jobs/", re.I),
     ATSType.LINKEDIN_EASY_APPLY, Difficulty.AUTO),
    (re.compile(r"linkedin\.com/apply/", re.I),
     ATSType.LINKEDIN_EASY_APPLY, Difficulty.AUTO),

    # ── Indeed ────────────────────────────────────────────────────────────────
    (re.compile(r"indeed\.com/", re.I),
     ATSType.INDEED, Difficulty.AUTO),
    (re.compile(r"indeed\.co\.", re.I),        # indeed.co.uk, indeed.co.in …
     ATSType.INDEED, Difficulty.AUTO),

    # ── Greenhouse ────────────────────────────────────────────────────────────
    (re.compile(r"(boards\.)?greenhouse\.io/", re.I),
     ATSType.GREENHOUSE, Difficulty.HYBRID),
    (re.compile(r"grnh\.se/", re.I),           # Greenhouse short-links
     ATSType.GREENHOUSE, Difficulty.HYBRID),

    # ── Lever ─────────────────────────────────────────────────────────────────
    (re.compile(r"(jobs\.)?lever\.co/", re.I),
     ATSType.LEVER, Difficulty.HYBRID),

    # ── Ashby ─────────────────────────────────────────────────────────────────
    (re.compile(r"ashbyhq\.com/", re.I),
     ATSType.ASHBY, Difficulty.HYBRID),
    (re.compile(r"jobs\.ashbyhq\.com/", re.I),
     ATSType.ASHBY, Difficulty.HYBRID),

    # ── Workday ───────────────────────────────────────────────────────────────
    (re.compile(r"myworkdayjobs\.com/", re.I),
     ATSType.WORKDAY, Difficulty.MANUAL),
    (re.compile(r"workday\.com/", re.I),
     ATSType.WORKDAY, Difficulty.MANUAL),
    (re.compile(r"wd\d+\.myworkdayjobs\.com/", re.I),
     ATSType.WORKDAY, Difficulty.MANUAL),

    # ── iCIMS ─────────────────────────────────────────────────────────────────
    (re.compile(r"icims\.com/", re.I),
     ATSType.ICIMS, Difficulty.MANUAL),
    (re.compile(r"careers\.icims\.com/", re.I),
     ATSType.ICIMS, Difficulty.MANUAL),
]

# Handler keys returned by route_application()
_HANDLER_MAP: dict[ATSType, str] = {
    ATSType.LINKEDIN_EASY_APPLY: "linkedin",
    ATSType.INDEED:              "indeed",
    ATSType.GREENHOUSE:          "greenhouse",
    ATSType.LEVER:               "lever",
    ATSType.ASHBY:               "external",
    ATSType.WORKDAY:             "external",
    ATSType.ICIMS:               "external",
    ATSType.EXTERNAL_UNKNOWN:    "external",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public functions
# ─────────────────────────────────────────────────────────────────────────────

def classify_job(url: str) -> tuple[ATSType, Difficulty]:
    """
    Classify a job posting URL by its ATS platform and automation difficulty.

    Parameters
    ----------
    url:
        Full job-posting URL, e.g. ``"https://boards.greenhouse.io/acme/jobs/123"``.

    Returns
    -------
    ``(ATSType, Difficulty)`` — the first matching rule wins; falls back to
    ``(ATSType.EXTERNAL_UNKNOWN, Difficulty.MANUAL)`` when no rule matches.
    """
    if not url:
        return ATSType.EXTERNAL_UNKNOWN, Difficulty.MANUAL

    for pattern, ats_type, difficulty in _RULES:
        if pattern.search(url):
            return ats_type, difficulty

    return ATSType.EXTERNAL_UNKNOWN, Difficulty.MANUAL


def route_application(job: dict) -> str:
    """
    Return the handler key for a job dict that has at least a ``"url"`` field.

    The handler key is a short string that callers use to dispatch to the
    right apply bot, e.g.:

    - ``"linkedin"``  → ``LinkedInApplyBot``
    - ``"indeed"``    → ``IndeedApplyBot``
    - ``"external"``  → flag for manual review

    Parameters
    ----------
    job:
        Dict with at minimum ``{"url": "https://..."}`` (and optionally
        pre-computed ``"ats_type"`` / ``"difficulty"`` keys from a prior
        :func:`classify_job` call).

    Returns
    -------
    Handler key string.
    """
    # Honour pre-classified values if already present
    raw_ats = job.get("ats_type")
    if raw_ats:
        try:
            ats_type = ATSType(raw_ats)
            return _HANDLER_MAP.get(ats_type, "external")
        except ValueError:
            pass

    ats_type, _ = classify_job(job.get("url", ""))
    return _HANDLER_MAP.get(ats_type, "external")
