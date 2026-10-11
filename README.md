# JobCrawler

A job application assistant: a browser extension that reads job listings and fills application forms, an API that scores listings against your profile, and a web dashboard for reviewing and tracking applications.

This is a personal project. It was never released publicly and I have been its only user.

## Components

| Directory | What it is | Stack |
|---|---|---|
| `api/` | REST API: auth, profiles, job scoring, form answers, billing | FastAPI, SQLAlchemy (async), Alembic, PostgreSQL or SQLite |
| `web/` | Dashboard: onboarding, review queue, applications, billing, settings | React 19, TypeScript, Vite, Tailwind CSS |
| `extension/` | Chrome extension (Manifest V3): scrapes listings, fills forms on LinkedIn, Greenhouse, Lever and Indeed | TypeScript, esbuild |
| `scripts/prod_test/` | Scripts that exercise a running API: auth flows, unique constraints, concurrency, ingest performance | Python |
| `legacy/` | The first version, a set of Python automation scripts | Python |

## How it works

1. The extension collects job cards from a search page and sends them to `POST /discovery/ingest`. The API removes duplicates and applies the user's company and keyword blacklists.
2. The API scores each remaining job against the user's profile with an LLM and puts it in a review queue.
3. The user approves jobs in the dashboard. On an application page, the extension scans the form, asks the API for answers, and fills the fields.
4. Each application is tracked with its status.

## Notable implementation details

- **Sessions.** The access token is kept in memory in the web app. The refresh token lives in an httpOnly cookie and is rotated on every use. Reusing an old refresh token revokes every token issued from that login. See `api/services/refresh_tokens.py`.
- **CSRF.** Cookie-based calls to `/auth/refresh` and `/auth/logout` require a double-submit token.
- **Rate limiting.** Auth endpoints are limited per IP and per email with a sliding window, stored in Redis when `REDIS_URL` is set and in memory otherwise. See `api/middleware/auth_throttle.py`.
- **Billing.** Razorpay payments are checked for signature, order ownership and amount. A unique constraint on the payment ID and a table of processed webhook event IDs keep a payment from being applied twice when the client callback and the webhook arrive together. See `api/routes/billing.py`.
- **Extension messaging.** The service worker rejects any message whose sender and origin are not on an allowlist for that message type. See `extension/src/background/service-worker.ts`.
- **Untrusted text.** Job descriptions are sanitised and wrapped in delimiters before they are placed in an LLM prompt. See `api/services/prompt_safety.py`.

## Running locally

Requirements: Python 3.12, Node.js 22.

### API

```bash
pip install -r api/requirements.txt
cp api/.env.example api/.env        # set JWT_SECRET_KEY (32+ characters) and one LLM provider key
alembic -c api/alembic.ini upgrade head
uvicorn api.main:app --reload
```

The API runs at `http://localhost:8000`. With no `DATABASE_URL` it uses a local SQLite file.

### Web

```bash
cd web
npm install
cp .env.example .env.development
npm run dev
```

### Extension

```bash
cd extension
npm install
npm run build
```

Load `extension/dist` in Chrome from `chrome://extensions` with Developer mode on.

## Tests

```bash
pytest api/tests          # API
cd extension && npm test  # extension
```

GitHub Actions runs the API tests, the web type check and build, and the extension build and tests on every push.

## Configuration

All settings are environment variables, listed in `api/.env.example` and `web/.env.example`. In production the API refuses to start if the JWT secret is shorter than 32 characters, if any allowed origin is not HTTPS, or if no extension ID is configured for CORS.

## A note on use

Automating applications may be against the terms of service of some job sites. I built this to learn and used it only on my own account. Check a site's terms before using anything like it.
