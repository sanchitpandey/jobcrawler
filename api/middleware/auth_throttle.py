"""
Auth-endpoint throttling — per-IP and per-email sliding window counters.

The dependency raises HTTP 429 when a caller exceeds the configured limit.

Backends (audit fix N6)
-----------------------
When ``settings.redis_url`` is set, counters are stored in Redis using a
sliding-window sorted-set per (bucket, key), so multi-worker / multi-pod
deployments share state and a redeploy does not zero counters. When unset
(or Redis is unreachable), the module falls back to per-process in-memory
deques — fine for single-worker dev / test.

Limits (defaults)
-----------------
login              : 10/15min per IP, 5/15min per email
register           : 5/hr per IP, 3/hr per email
forgot-password    : 5/hr per email, 20/hr per IP
reset-password     : 10/15min per IP, 5/15min per email
verify-email       : 10/15min per user (enforced by user-row counter)

Note: this is the network-layer guard. Per-account brute force on the 6-digit
reset/verification code is additionally bounded by `User.verification_attempts`
in routes/auth.py, which invalidates the code after N failures.
"""

from __future__ import annotations

import ipaddress
import time
from collections import defaultdict, deque
from functools import lru_cache
from typing import Deque, NamedTuple

from fastapi import HTTPException, Request, status

from api.config import get_settings
from api.logger import get_logger

log = get_logger(__name__)


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
    # Account export + delete. Caps per-IP so a stolen access token can't be
    # used to repeatedly hammer either endpoint.
    "account_destructive": _Bucket(window_seconds=3600, max_hits=10),
}

# Per-key (email / user) buckets
_KEY_BUCKETS: dict[str, _Bucket] = {
    "login": _Bucket(window_seconds=900, max_hits=5),
    # Audit fix N7: per-email register cap stops mail-bombing a victim with
    # verification codes even when the per-IP cap is bypassed (e.g. via N4).
    "register": _Bucket(window_seconds=3600, max_hits=3),
    "forgot": _Bucket(window_seconds=3600, max_hits=5),
    "reset": _Bucket(window_seconds=900, max_hits=5),
    "verify": _Bucket(window_seconds=900, max_hits=10),
    # Per-user cap on export + delete. 5/hr lets a confused user retry a few
    # times but stops a stolen-token loop from exfiltrating data repeatedly.
    "account_destructive": _Bucket(window_seconds=3600, max_hits=5),
}

# {bucket_name: {key: deque[hit_timestamp]}} — in-memory fallback
_hits: dict[str, dict[str, Deque[float]]] = defaultdict(lambda: defaultdict(deque))

# Module-level Redis state. We probe lazily on first ``enforce`` and disable
# the backend on any error so failures degrade to in-memory rather than 5xx.
_redis_client = None  # type: ignore[assignment]
_redis_initialised = False
_redis_disabled = False


async def _get_redis():  # -> redis.asyncio.Redis | None
    """Return a connected async Redis client, or None to use the in-memory path."""
    global _redis_client, _redis_initialised, _redis_disabled
    if _redis_disabled:
        return None
    if _redis_initialised:
        return _redis_client

    _redis_initialised = True
    url = (get_settings().redis_url or "").strip()
    if not url:
        _redis_disabled = True
        return None
    try:
        import redis.asyncio as aioredis  # type: ignore

        client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
        await client.ping()
        _redis_client = client
        log.info("auth_throttle: Redis backend enabled (%s)", url)
        return client
    except Exception as exc:  # noqa: BLE001 — any failure falls back
        log.warning("auth_throttle: Redis unavailable, falling back to in-memory (%s)", exc)
        _redis_disabled = True
        _redis_client = None
        return None


@lru_cache(maxsize=1)
def _trusted_proxy_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """Parse settings.trusted_proxies once into a tuple of ipaddress networks.

    Invalid entries are silently dropped — an operator typo should not crash
    the auth path, but the empty result will then make ``_client_ip`` ignore
    XFF entirely, which is the safe fallback.
    """
    out: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for raw in get_settings().trusted_proxies:
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(ipaddress.ip_network(raw, strict=False))
        except ValueError:
            continue
    return tuple(out)


def _is_trusted_proxy(ip_str: str) -> bool:
    nets = _trusted_proxy_networks()
    if not nets:
        return False
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(ip in net for net in nets)


def _client_ip(request: Request) -> str:
    """Resolve the real client IP.

    Audit fix N4: previously the first ``X-Forwarded-For`` value was trusted
    blindly, letting any caller rotate the header to dodge per-IP rate
    limits. We now require an explicit ``TRUSTED_PROXIES`` allowlist (CIDRs
    of the reverse proxy / CDN front door). If unset, XFF is ignored. If
    set, we walk the XFF chain right-to-left and return the first hop that
    is NOT in the trusted set — that is the rightmost untrusted client.
    """
    socket_host = request.client.host if request.client else "unknown"

    # Only honour proxy headers when (a) we have a trusted-proxies allowlist
    # AND (b) the immediate peer is one of those proxies. Otherwise the
    # caller could be sending the header directly.
    if _trusted_proxy_networks() and _is_trusted_proxy(socket_host):
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            hops = [h.strip() for h in fwd.split(",") if h.strip()]
            # Walk right-to-left, skipping trusted hops; first untrusted is real client.
            for hop in reversed(hops):
                if not _is_trusted_proxy(hop):
                    return hop
            # All hops were trusted — fall back to socket peer.
        real_ip = request.headers.get("x-real-ip")
        if real_ip and not _is_trusted_proxy(real_ip.strip()):
            return real_ip.strip()

    return socket_host


def _check_memory(bucket_name: str, key: str, bucket: _Bucket) -> tuple[bool, int]:
    """In-memory sliding-window check. Returns (allowed, seconds_until_reset)."""
    now = time.monotonic()
    cutoff = now - bucket.window_seconds
    q = _hits[bucket_name][key]
    while q and q[0] < cutoff:
        q.popleft()
    if len(q) >= bucket.max_hits:
        return False, max(1, int(bucket.window_seconds - (now - q[0])))
    q.append(now)
    return True, bucket.window_seconds


async def _check_redis(
    client, bucket_name: str, key: str, bucket: _Bucket
) -> tuple[bool, int]:
    """Redis sliding-window check via a sorted set. Returns (allowed, seconds_until_reset).

    The set stores timestamps as both score and unique member (with a nonce
    suffix to allow two hits at the same millisecond). We:
      1. Strip entries older than the window.
      2. Read the remaining count.
      3. If under cap, add this hit and refresh TTL.

    Failures (network blip, server gone) fall back to in-memory.
    """
    redis_key = f"throttle:{bucket_name}:{key}"
    now_ms = int(time.time() * 1000)
    cutoff_ms = now_ms - bucket.window_seconds * 1000
    try:
        pipe = client.pipeline(transaction=False)
        pipe.zremrangebyscore(redis_key, 0, cutoff_ms)
        pipe.zcard(redis_key)
        _, count = await pipe.execute()
        if count >= bucket.max_hits:
            oldest = await client.zrange(redis_key, 0, 0, withscores=True)
            if oldest:
                _, oldest_score = oldest[0]
                reset_in = max(1, bucket.window_seconds - int((now_ms - oldest_score) / 1000))
            else:
                reset_in = bucket.window_seconds
            return False, reset_in
        # Record this hit; nonce keeps members unique within the same millisecond.
        import secrets as _secrets

        member = f"{now_ms}:{_secrets.token_hex(4)}"
        pipe = client.pipeline(transaction=False)
        pipe.zadd(redis_key, {member: now_ms})
        pipe.expire(redis_key, bucket.window_seconds + 5)
        await pipe.execute()
        return True, bucket.window_seconds
    except Exception as exc:  # noqa: BLE001
        global _redis_disabled
        log.warning("auth_throttle: Redis check failed, falling back (%s)", exc)
        _redis_disabled = True
        return _check_memory(bucket_name, key, bucket)


async def _check(bucket_name: str, key: str, bucket: _Bucket) -> tuple[bool, int]:
    client = await _get_redis()
    if client is not None:
        return await _check_redis(client, bucket_name, key, bucket)
    return _check_memory(bucket_name, key, bucket)


async def enforce(request: Request, bucket_name: str, key: str | None = None) -> None:
    """Raise 429 if the IP (and optionally the per-account key) is over budget."""
    ip = _client_ip(request)
    ip_bucket = _IP_BUCKETS.get(bucket_name)
    if ip_bucket:
        allowed, reset_in = await _check(f"ip:{bucket_name}", ip, ip_bucket)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again later.",
                headers={"Retry-After": str(reset_in)},
            )
    if key is not None:
        key_bucket = _KEY_BUCKETS.get(bucket_name)
        if key_bucket:
            allowed, reset_in = await _check(f"key:{bucket_name}", key.lower(), key_bucket)
            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests for this account. Try again later.",
                    headers={"Retry-After": str(reset_in)},
                )


def reset_for_tests() -> None:
    """Clear all counters — invoked from test fixtures."""
    global _redis_initialised, _redis_disabled, _redis_client
    _hits.clear()
    _trusted_proxy_networks.cache_clear()
    # Force re-probe of Redis on next call so a test that swaps the URL
    # picks up the change. The fallback path stays fast either way.
    _redis_initialised = False
    _redis_disabled = False
    _redis_client = None
