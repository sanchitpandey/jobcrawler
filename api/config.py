from functools import lru_cache
from pathlib import Path
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./jobcrawler.db"

    # Redis — empty means in-memory rate-limit buckets only (single-worker dev).
    # Set REDIS_URL in env to share auth-throttle counters across workers / pods
    # (audit fix N6).
    redis_url: str = ""

    # JWT — must be explicitly provided in every environment. Audit fix #14:
    # removed the committed insecure default so a missing JWT_SECRET_KEY
    # fails fast at startup instead of silently issuing forgeable tokens.
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24      # 24 h
    jwt_refresh_token_expire_days: int = 30
    # Issuer + audience claims (audit fix L1). The issuer ties a token to a
    # specific deployment (so a leaked dev secret can't forge prod tokens even
    # if the HS256 key was accidentally reused), and the audience pins tokens
    # to this API (so a token minted for a sibling service is rejected here).
    jwt_issuer: str = "jobcrawler-api"
    jwt_audience: str = "jobcrawler-api"

    # LLM providers
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    cerebras_api_key: str = ""
    together_api_key: str = ""

    # CORS — comma-separated in env: ALLOWED_ORIGINS="http://localhost:3000,chrome-extension://abc"
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://jobcrawler.dev",
        "https://www.jobcrawler.dev",
    ]
    # Comma-separated list of published Chrome extension IDs allowed to call the
    # API with credentials. Empty in production fails the startup check (fix #11:
    # CORS regex previously trusted ALL chrome-extension:// origins).
    allowed_extension_ids: list[str] = []

    # Subscription limits
    free_tier_weekly_limit: int = 5
    free_tier_daily_llm_calls: int = 50   # max LLM endpoint calls/day for free users

    # Razorpay (India payments)
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    email_from: str = "JobCrawler <noreply@jobcrawler.dev>"

    # Sentry
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.2   # 20% of requests traced in prod

    # App
    app_env: str = "development"
    debug: bool = False

    # Reverse-proxy / CDN front-door allowlist for trusted X-Forwarded-For
    # parsing (audit fix N4). Comma-separated CIDRs in env (e.g.
    # TRUSTED_PROXIES="10.0.0.0/8,172.16.0.0/12"). When EMPTY, the auth
    # throttle ignores XFF entirely and uses ``request.client.host``, so a
    # client cannot rotate XFF to bypass per-IP rate limits in dev/test or
    # when the API is exposed directly. When set, the rightmost hop NOT in
    # the allowlist is treated as the real client IP.
    trusted_proxies: list[str] = []

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _production_checks(self) -> "Settings":
        if len(self.jwt_secret_key) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be set to a random string of at least 32 characters"
            )
        if self.app_env == "production":
            insecure = [o for o in self.allowed_origins if not o.startswith(("https://", "chrome-extension://"))]
            if insecure:
                raise ValueError(
                    f"Non-HTTPS origins not allowed in production: {insecure}"
                )
            if not self.allowed_extension_ids:
                raise ValueError(
                    "ALLOWED_EXTENSION_IDS must list the production extension ID(s) "
                    "to scope chrome-extension CORS in production"
                )
        return self

    @property
    def extension_origin_regex(self) -> str | None:
        """Build a strict chrome-extension allowlist regex from configured IDs.

        Returns None when no extension IDs are configured (dev convenience —
        production startup requires at least one, see ``_production_checks``).
        """
        ids = [eid.strip() for eid in self.allowed_extension_ids if eid.strip()]
        if not ids:
            return None
        return r"^chrome-extension://(" + "|".join(ids) + r")$"


@lru_cache
def get_settings() -> Settings:
    return Settings()
