"""Password policy — minimum length plus breach-list check (audit #13).

Length is enforced by the Pydantic request schema (>=12). This module adds a
defense-in-depth check against the most common compromised passwords:

1. A small embedded top-N denylist catches the worst offenders (and keeps the
   check working in offline tests / CI without a network round-trip).
2. The HIBP "Pwned Passwords" Range API
   (https://api.pwnedpasswords.com/range/{prefix}) is used in production when
   reachable. K-anonymity: only the first 5 hex chars of SHA-1(password) leave
   the server; the API returns all hash suffixes seen in breach corpora and we
   match locally.

A network failure must NOT block registration — it falls back to the embedded
list and logs a warning. A confirmed match raises HTTPException(400).
"""

from __future__ import annotations

import hashlib

import httpx
from fastapi import HTTPException, status

from api.config import get_settings
from api.logger import get_logger

log = get_logger(__name__)

# Top compromised passwords — guards offline tests + first line of defense.
# Length-12 minimum already removes most weak passwords; this list targets the
# common ≥12 ones that still show up in breach corpora (rockyou, etc.).
_EMBEDDED_BREACHED: frozenset[str] = frozenset(
    pw.lower()
    for pw in (
        "password1234",
        "qwerty123456",
        "qwertyuiop12",
        "1q2w3e4r5t6y",
        "1qaz2wsx3edc",
        "passw0rd1234",
        "letmein12345",
        "iloveyou1234",
        "welcome12345",
        "admin1234567",
        "password!1234",
        "password@123",
        "p@ssw0rd1234",
        "monkey1234567",
        "dragon1234567",
        "football1234",
        "baseball1234",
        "trustno1234",
        "abc123456789",
        "123456789012",
        "111111111111",
        "qazwsxedcrfv",
        "zaq12wsxcde3",
    )
)

# Anything seen more than this many times in HIBP is considered compromised.
_HIBP_COUNT_THRESHOLD = 1
_HIBP_TIMEOUT_SECONDS = 2.0
_HIBP_URL = "https://api.pwnedpasswords.com/range/{prefix}"


def _embedded_breached(password: str) -> bool:
    return password.lower() in _EMBEDDED_BREACHED


def _hibp_breached(password: str) -> bool:
    """Return True if HIBP says the password has been seen in a breach.

    Returns False on any network/parse failure — caller falls back to the
    embedded list rather than locking users out during an outage.
    """
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        resp = httpx.get(
            _HIBP_URL.format(prefix=prefix),
            timeout=_HIBP_TIMEOUT_SECONDS,
            headers={"Add-Padding": "true", "User-Agent": "jobcrawler-auth"},
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("hibp lookup failed; falling back to embedded list", extra={"error": str(exc)})
        return False

    for line in resp.text.splitlines():
        # "SUFFIX:COUNT" — padded rows have COUNT == 0 and must be ignored.
        hash_suffix, _, count_str = line.partition(":")
        if hash_suffix.strip().upper() != suffix:
            continue
        try:
            count = int(count_str.strip())
        except ValueError:
            continue
        return count >= _HIBP_COUNT_THRESHOLD
    return False


def assert_password_acceptable(password: str) -> None:
    """Raise HTTPException(400) if the password is in a breach corpus.

    The embedded denylist always runs. The HIBP network lookup runs only when
    ``app_env == "production"`` so the test suite and offline dev work do not
    depend on external connectivity (a network failure already falls back to
    the embedded list, but skipping the call entirely is faster and keeps the
    happy path deterministic).
    """
    if _embedded_breached(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password has appeared in known data breaches. Choose a different one.",
        )
    if get_settings().app_env != "production":
        return
    if _hibp_breached(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password has appeared in known data breaches. Choose a different one.",
        )
