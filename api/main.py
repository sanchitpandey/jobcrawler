from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.logger import get_logger, setup_logging
from api.middleware.logging import RequestLoggingMiddleware
from api.models.base import engine
from api.models import Base  # noqa: F401 — imports all models so metadata is populated
from api.routes import auth, forms, jobs, profiles

settings = get_settings()

# Configure logging before the first log line (import-time loggers use whatever
# basicConfig set; routes and handlers will use this config).
setup_logging(app_env=settings.app_env, debug=settings.debug)
log = get_logger(__name__)


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

# Middleware order: outermost first (CORS → logging → route handlers)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth.router)
app.include_router(forms.router)
app.include_router(jobs.router)
app.include_router(profiles.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
