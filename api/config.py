from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_JWT_DEFAULT = "change-me-in-production-use-32-plus-random-chars"


class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite+aiosqlite:///./jobcrawler.db"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = _INSECURE_JWT_DEFAULT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24      # 24 h
    jwt_refresh_token_expire_days: int = 30

    # LLM providers
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    cerebras_api_key: str = ""
    together_api_key: str = ""

    # CORS — comma-separated in env: ALLOWED_ORIGINS="http://localhost:3000,chrome-extension://abc"
    allowed_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # Subscription limits
    free_tier_weekly_limit: int = 5
    free_tier_daily_llm_calls: int = 50   # max LLM endpoint calls/day for free users

    # App
    app_env: str = "development"
    debug: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _production_checks(self) -> "Settings":
        if self.app_env == "production":
            if self.jwt_secret_key == _INSECURE_JWT_DEFAULT or len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a random string of at least 32 characters in production"
                )
            insecure = [o for o in self.allowed_origins if not o.startswith(("https://", "chrome-extension://"))]
            if insecure:
                raise ValueError(
                    f"Non-HTTPS origins not allowed in production: {insecure}"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
