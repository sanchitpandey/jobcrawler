"""
Auth-endpoint throttling — per-IP and per-email sliding window counters.

The dependency raises HTTP 429 when a caller exceeds the configured limit.
Counters live in-process (best-effort: per-worker). For multi-worker / multi-pod
deployments swap the backing store for Redis — the API surface is unchanged.

Limits (defaults)
-----------------
login              : 10/15min per IP, 5/15min per email
register           : 5/hr per IP
forgot-password    : 5/hr per email, 20/hr per IP
reset-password     : 10/15min per IP, 5/15min per email
verify-email       : 10/15min per user (enforced by user-row counter)

Note: this is the network-layer guard. Per-account brute force on the 6-digit
reset/verification code is additionally bounded by `User.verification_attempts`
in routes/auth.py, which invalidates the code after N failures.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, NamedTuple

from fastapi import HTTPException, Request, status


class _Bucket(NamedTuple):
    window_seconds: int
    max_hits: int


# Per-IP buckets
_IP_BUCKETS: dict[str, _Bucket] = {
    "login": _Bucket(window_seconds=900, max_hits=10),
    "register": _Bucket(window_seconds=3600, max_hits=5),
    "forgot": _Bucket(window_seconds=3600, max_hits=20),
    "reset": _Bucket(window_seconds=900, max_hits=10),
    "verify": _Bucket(window_seconds=900, max_hits=20),
}

# Per-key (email / user) buckets
_KEY_BUCKETS: dict[str, _Bucket] = {
    "login": _Bucket(window_seconds=900, max_hits=5),
    "forgot": _Bucket(window_seconds=3600, max_hits=5),
    "reset": _Bucket(window_seconds=900, max_hits=5),
    "verify": _Bucket(window_seconds=900, max_hits=10),
}

# {bucket_name: {key: deque[hit_timestamp]}}
_hits: dict[str, dict[str, Deque[float]]] = defaultdict(lambda: defaultdict(deque))


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        # First value is the original client
        return fwd.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def _check(bucket_name: str, key: str, bucket: _Bucket) -> bool:
    """Return True if allowed; False if rate-limited. Records a hit when allowed."""
    now = time.monotonic()
    cutoff = now - bucket.window_seconds
    q = _hits[bucket_name][key]
    # Trim expired entries
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= bucket.max_hits:
        return False
    q.append(now)
    return True


def _seconds_until_reset(bucket_name: str, key: str, bucket: _Bucket) -> int:
    q = _hits[bucket_name].get(key)
    if not q:
        return 1
    return max(1, int(bucket.window_seconds - (time.monotonic() - q[0])))


def enforce(request: Request, bucket_name: str, key: str | None = None) -> None:
    """Raise 429 if the IP (and optionally the per-account key) is over budget."""
    ip = _client_ip(request)
    ip_bucket = _IP_BUCKETS.get(bucket_name)
    if ip_bucket and not _check(f"ip:{bucket_name}", ip, ip_bucket):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please slow down and try again later.",
            headers={"Retry-After": str(_seconds_until_reset(f"ip:{bucket_name}", ip, ip_bucket))},
        )
    if key is not None:
        key_bucket = _KEY_BUCKETS.get(bucket_name)
        if key_bucket and not _check(f"key:{bucket_name}", key.lower(), key_bucket):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests for this account. Try again later.",
                headers={"Retry-After": str(_seconds_until_reset(f"key:{bucket_name}", key.lower(), key_bucket))},
            )


def reset_for_tests() -> None:
    """Clear all counters — invoked from test fixtures."""
    _hits.clear()
