"""Section 13.2 — empirical check that our request-logging middleware does
not include passwords/tokens in formatted output.

We:
  1. Boot a single Starlette app with our RequestLoggingMiddleware.
  2. Capture the JSON logger's stdout.
  3. Issue requests carrying sensitive material in body/header/query.
  4. Assert the captured logs contain none of it.
"""
from __future__ import annotations
import io
import json
import logging
import sys
import contextlib

sys.path.insert(0, ".")

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from api.logger import setup_logging, get_logger, JsonFormatter
from api.middleware.logging import RequestLoggingMiddleware


buf = io.StringIO()
handler = logging.StreamHandler(buf)
handler.setFormatter(JsonFormatter())
logging.getLogger().handlers = [handler]
logging.getLogger().setLevel(logging.INFO)

async def echo(req: Request):
    return JSONResponse({"ok": True})

app = Starlette(routes=[Route("/echo", echo, methods=["POST", "GET"])])
app.add_middleware(RequestLoggingMiddleware)

c = TestClient(app)
SECRET_PW = "DefinitelySecret-Pw-AStrongPassword!2026"
SECRET_TOKEN = "eyJalg-PRETEND-FULL-JWT-1234567890abcdef"
SECRET_RZP = "rzp_test_FAKEKEYSHOULD-NOT-LEAK"

# Send sensitive material in body
c.post("/echo", json={"email": "x@y.com", "password": SECRET_PW})
# In Authorization header
c.get("/echo", headers={"Authorization": f"Bearer {SECRET_TOKEN}"})
# In query string
c.get(f"/echo?razorpay_secret={SECRET_RZP}")

log_text = buf.getvalue()
print(f"--- captured {len(log_text)} bytes of log lines ---")
print(log_text[:2000])
print("--- checks ---")
ok = True
for label, needle in [("password body", SECRET_PW),
                       ("full JWT", SECRET_TOKEN),
                       ("razorpay key", SECRET_RZP)]:
    if needle in log_text:
        print(f"FAIL: '{label}' leaked into logs")
        ok = False
    else:
        print(f"OK: '{label}' not in logs")
sys.exit(0 if ok else 1)
