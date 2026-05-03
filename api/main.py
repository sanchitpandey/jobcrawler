from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

import sentry_sdk
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from api.config import get_settings
from api.logger import get_logger, setup_logging
from api.middleware.logging import RequestLoggingMiddleware
from api.models.base import engine, get_db
from api.models import Base  # noqa: F401 — imports all models so metadata is populated
from api.routes import auth, billing, discovery, forms, jobs, profiles

settings = get_settings()

# Configure logging before the first log line.
setup_logging(app_env=settings.app_env, debug=settings.debug)
log = get_logger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate if settings.app_env == "production" else 0.0,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(
                level=logging.WARNING,   # breadcrumbs from WARNING+
                event_level=logging.ERROR,  # send to Sentry from ERROR+
            ),
        ],
        send_default_pii=False,
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info(
        "JobCrawler API starting",
        extra={"env": settings.app_env, "debug": settings.debug},
    )
    # Create tables on startup (dev convenience; prod uses Alembic)
    if settings.app_env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    log.info("JobCrawler API shutting down")
    await engine.dispose()


app = FastAPI(
    title="JobCrawler API",
    description="AI job application automation backend.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

# Middleware order: outermost first (security headers → CORS → logging → route handlers)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(discovery.router)
app.include_router(forms.router)
app.include_router(jobs.router)
app.include_router(profiles.router)


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "db": "connected"}
