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
# common ≥12-char ones that still show up in breach corpora (rockyou2021, HIBP
# v8 top-N, NCSC's bad-password list). Audit N11: expanded so the offline
# fallback is meaningful when HIBP is unreachable.
_EMBEDDED_BREACHED: frozenset[str] = frozenset(
    pw.lower()
    for pw in (
        # Sequential digits / keyboard walks (12+ chars)
        "123456789012",
        "1234567890123",
        "12345678901234",
        "123456789012345",
        "1234567890123456",
        "111111111111",
        "000000000000",
        "121212121212",
        "112233445566",
        "987654321012",
        "qwertyuiop12",
        "qwertyuiop[]",
        "qwertyuiopasdf",
        "asdfghjkl123",
        "asdfghjklzxc",
        "zxcvbnm12345",
        "qwerty123456",
        "qwerty1234567",
        "qwerty12345678",
        "qazwsxedcrfv",
        "qazwsxedcrfvtgb",
        "1q2w3e4r5t6y",
        "1q2w3e4r5t6y7u",
        "1qaz2wsx3edc",
        "1qaz2wsx3edc4rfv",
        "zaq12wsxcde3",
        "zaq1xsw2cde3",
        # "password" variants
        "password1234",
        "password12345",
        "password123456",
        "password1!23",
        "password!1234",
        "password@123",
        "password@1234",
        "password#123",
        "password2023",
        "password2024",
        "password2025",
        "password2026",
        "passwordpassword",
        "p@ssw0rd1234",
        "p@$$w0rd1234",
        "passw0rd1234",
        "passw0rd!234",
        "passw0rd@123",
        # Common base words + suffixes
        "letmein12345",
        "letmein123456",
        "iloveyou1234",
        "iloveyou12345",
        "iloveyou2024",
        "welcome12345",
        "welcome123456",
        "welcome2024!",
        "welcomehome12",
        "admin1234567",
        "admin12345678",
        "administrator1",
        "administrator!",
        "monkey1234567",
        "monkey12345678",
        "dragon1234567",
        "dragon12345678",
        "football1234",
        "football12345",
        "baseball1234",
        "baseball12345",
        "basketball12",
        "basketball123",
        "trustno1234",
        "trustno12345",
        "superman1234",
        "superman12345",
        "batman1234567",
        "starwars1234",
        "starwars12345",
        "pokemon123456",
        "minecraft1234",
        "minecraft12345",
        "princess1234",
        "princess12345",
        "sunshine1234",
        "sunshine12345",
        "thunder1234567",
        "computer1234",
        "computer12345",
        "internet1234",
        "internet12345",
        # Months / years / dates
        "january12345",
        "february2024",
        "summer2024!!",
        "winter2024!!",
        "spring2024!!",
        "autumn2024!!",
        # alphanumeric drifts
        "abc123456789",
        "abcd12345678",
        "abcdef123456",
        "abcdefghijkl",
        "abcdefgh1234",
        "aaaaaaaa1234",
        "aaaaaaaaaaaa",
        # Common phrases
        "ihatemyjob123",
        "iloveyouxxxx",
        "fuckyou12345",
        "letmeinplease",
        "changeme1234",
        "changeme12345",
        "default123456",
        "qwerty!@#123",
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
