"""
Email delivery via Resend (https://resend.com).

Uses httpx directly — no extra dependency beyond what's already in requirements.txt.
Set RESEND_API_KEY in .env to enable. Without it, sends are skipped with a warning
so local dev and tests work without email config.
"""

import asyncio

import httpx

from api.config import get_settings
from api.logger import get_logger

log = get_logger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


async def _send(*, to: str, subject: str, html: str, text: str) -> None:
    settings = get_settings()
    if not settings.resend_api_key:
        log.warning("RESEND_API_KEY not set — email not sent", extra={"to": to, "subject": subject})
        return

    payload = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
            if not resp.is_success:
                log.error(
                    "email delivery failed: %s %s",
                    resp.status_code,
                    resp.text,
                    extra={"to": to, "subject": subject},
                )
                return
            log.info("email sent", extra={"to": to, "subject": subject, "resend_id": resp.json().get("id")})
    except Exception:
        log.exception("email delivery failed", extra={"to": to, "subject": subject})


def send_verification_email(to: str, code: str) -> asyncio.Task:
    """Fire-and-forget: returns a Task so the caller can await it or ignore it."""
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px">
      <h2 style="margin:0 0 8px">Verify your JobCrawler account</h2>
      <p style="color:#555;margin:0 0 24px">Enter the code below in the app. It expires in 15 minutes.</p>
      <div style="font-size:36px;font-weight:700;letter-spacing:8px;text-align:center;
                  padding:24px;background:#f4f4f5;border-radius:8px">{code}</div>
      <p style="color:#888;font-size:12px;margin:24px 0 0">
        If you didn't create a JobCrawler account, you can ignore this email.
      </p>
    </div>
    """
    text = f"Your JobCrawler verification code is: {code}\n\nIt expires in 15 minutes."
    return asyncio.create_task(
        _send(to=to, subject="Your JobCrawler verification code", html=html, text=text)
    )


def send_password_reset_email(to: str, code: str) -> asyncio.Task:
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:32px">
      <h2 style="margin:0 0 8px">Reset your JobCrawler password</h2>
      <p style="color:#555;margin:0 0 24px">Use this code to reset your password. It expires in 15 minutes.</p>
      <div style="font-size:36px;font-weight:700;letter-spacing:8px;text-align:center;
                  padding:24px;background:#f4f4f5;border-radius:8px">{code}</div>
      <p style="color:#888;font-size:12px;margin:24px 0 0">
        If you didn't request a password reset, you can ignore this email.
      </p>
    </div>
    """
    text = f"Your JobCrawler password reset code is: {code}\n\nIt expires in 15 minutes."
    return asyncio.create_task(
        _send(to=to, subject="Reset your JobCrawler password", html=html, text=text)
    )
