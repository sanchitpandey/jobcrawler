FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps for psycopg2 / asyncpg (PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create non-root user
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

# Run migrations then start server.
# PORT and WEB_CONCURRENCY are injected by Railway (and other PaaS).
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-2}"]
