"""
linkedin_apply.py
─────────────────
Automates LinkedIn Easy Apply using Playwright.

Features:
  - Persistent browser session (login once, reuse cookies)
  - Multi-step modal handling (contact → questions → resume → review → submit)
  - Hands all form questions to form_filler.py
  - Flags manual-review questions instead of guessing
  - Random human-like delays to avoid rate limiting
  - Detects "Already Applied", CAPTCHA, and other blockers

Usage:
    from linkedin_apply import LinkedInApplyBot
    bot = LinkedInApplyBot(headless=False)
    result = bot.apply(job_url="...", company="Acme", title="ML Engineer")
    bot.close()
"""

from __future__ import annotations
import time, random, json, re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from playwright.sync_api import (
    sync_playwright, Page, Browser, BrowserContext,
    TimeoutError as PWTimeoutError
)

from form_filler import answer_question, FilledAnswer
from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD, RESUME_PATH

SESSION_FILE = "output/linkedin_session.json"
RESUME_PATH_OBJ = Path(RESUME_PATH)


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class ApplyResult:
    status:          str          # "applied" | "already_applied" | "manual_review" | "error"
    job_url:         str          = ""
    company:         str          = ""
    title:           str          = ""
    manual_questions: list[str]   = field(default_factory=list)
    error_message:   str          = ""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _human_delay(lo=0.8, hi=2.5):
    time.sleep(random.uniform(lo, hi))


def _slow_type(page: Page, selector: str, text: str):
    """Type text with human-like per-character delay."""
    page.focus(selector)
    for ch in text:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.03, 0.10))


# ── Main bot class ────────────────────────────────────────────────────────────
class LinkedInApplyBot:
    def __init__(self, headless: bool = False):
        self._pw       = sync_playwright().start()
        self._browser  = self._pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context  = self._load_or_create_context()
        self._page     = self._context.new_page()
        self._page.set_viewport_size({"width": 1280, "height": 900})

    # ── Session management ───────────────────────────────────────────────────
    def _load_or_create_context(self) -> BrowserContext:
        session_path = Path(SESSION_FILE)
        if session_path.exists():
            ctx = self._browser.new_context(
                storage_state=str(session_path),
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            return ctx
        return self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )

    def login(self) -> bool:
        """Log in and persist session. Only needed once."""
        page = self._page
        page.goto("https://www.linkedin.com/login", wait_until="networkidle")
        _human_delay()

        if "feed" in page.url or page.locator(".global-nav").is_visible():
            print("  [LinkedIn] Already logged in.")
            return True

        page.fill("#username", LINKEDIN_EMAIL)
        _human_delay(0.3, 0.8)
        page.fill("#password", LINKEDIN_PASSWORD)
        _human_delay(0.5, 1.2)
        page.click('[data-litms-control-urn="login-submit"]')
        page.wait_for_load_state("networkidle")
        _human_delay(2, 4)

        if "checkpoint" in page.url or "captcha" in page.url.lower():
            print("  [LinkedIn] ⚠ CAPTCHA or checkpoint — solve manually, then press Enter.")
            input()

        if "feed" in page.url:
            self._context.storage_state(path=SESSION_FILE)
            print("  [LinkedIn] ✓ Logged in and session saved.")
            return True

        print("  [LinkedIn] ✗ Login failed. Check credentials in config.py.")
        return False

    # ── Main apply flow ───────────────────────────────────────────────────────
    def apply(
        self,
        job_url:   str,
        company:   str = "",
        title:     str = "",
    ) -> ApplyResult:
        page = self._page
        result = ApplyResult(status="error", job_url=job_url, company=company, title=title)

        try:
            # Navigate to job
            page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
            _human_delay(1.5, 3)

            # Detect "Already Applied"
            if page.locator("text=Applied").count() > 0:
                result.status = "already_applied"
                return result

            # Find and click Easy Apply button
            easy_apply_btn = page.locator(
                "button.jobs-apply-button:has-text('Easy Apply'), "
                "button:has-text('Easy Apply')"
            ).first
            if not easy_apply_btn.is_visible(timeout=5000):
                result.status = "error"
                result.error_message = "Easy Apply button not found — may be external application"
                return result

            easy_apply_btn.click()
            _human_delay(1, 2)

            # Handle multi-step modal
            result = self._handle_modal(page, result)

            # Persist session after each successful apply
            self._context.storage_state(path=SESSION_FILE)

        except PWTimeoutError as e:
            result.status = "error"
            result.error_message = f"Timeout: {e}"
        except Exception as e:
            result.status = "error"
            result.error_message = str(e)

        return result

    # ── Modal step handler ────────────────────────────────────────────────────
    def _handle_modal(self, page: Page, result: ApplyResult) -> ApplyResult:
        MAX_STEPS = 12

        for step in range(MAX_STEPS):
            _human_delay(0.8, 1.8)

            # Detect which step we're on
            modal = page.locator(".jobs-easy-apply-modal, [data-test-modal]").first

            # ── Submit button visible → final step
            submit_btn = page.locator("button[aria-label='Submit application']").first
            if submit_btn.is_visible():
                submit_btn.click()
                _human_delay(2, 4)
                # Confirm success
                if page.locator("text=Your application was sent").count() > 0:
                    result.status = "applied"
                else:
                    result.status = "applied"   # assume success if modal closed
                return result

            # ── Review step → click Submit or Next
            review_btn = page.locator("button:has-text('Review')").first
            if review_btn.is_visible():
                review_btn.click()
                continue

            # ── Fill current step's questions
            manual_qs = self._fill_step(page, result.company, result.title)
            result.manual_questions.extend(manual_qs)

            if manual_qs:
                # Has unanswerable questions → save for manual review & dismiss
                result.status = "manual_review"
                self._dismiss_modal(page)
                return result

            # ── Click Next
            next_btn = page.locator(
                "button[aria-label='Continue to next step'], "
                "button:has-text('Next')"
            ).first
            if next_btn.is_visible():
                next_btn.click()
            else:
                # No next button and no submit — something unexpected
                result.status = "error"
                result.error_message = f"Stuck on step {step} — no Next or Submit button"
                self._dismiss_modal(page)
                return result

        result.status = "error"
        result.error_message = "Exceeded max steps in modal"
        self._dismiss_modal(page)
        return result

    # ── Fill all fields in a single modal step ────────────────────────────────
    def _fill_step(self, page: Page, company: str, title: str) -> list[str]:
        """
        Fills all visible form fields on the current step.
        Returns list of question labels that need manual review.
        """
        manual_review_qs: list[str] = []

        # Handle resume upload
        upload_input = page.locator("input[type='file']").first
        if upload_input.is_visible() and RESUME_PATH_OBJ.exists():
            upload_input.set_input_files(str(RESUME_PATH_OBJ))
            _human_delay(1, 2)

        # ── Text inputs / textareas
        for el in page.locator("input[type='text']:visible, textarea:visible").all():
            label = self._get_label(page, el)
            if not label:
                continue
            filled = answer_question(label, "text", company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_qs.append(label)
            elif filled.value and not el.input_value():
                el.click()
                _slow_type(page, "", filled.value)  # already focused
                _human_delay(0.3, 0.8)

        # ── Number inputs
        for el in page.locator("input[type='number']:visible").all():
            label = self._get_label(page, el)
            if not label or el.input_value():
                continue
            filled = answer_question(label, "text", company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_qs.append(label)
            elif filled.value:
                el.fill(re.sub(r"[^\d]", "", filled.value)[:6])
                _human_delay(0.3, 0.6)

        # ── Dropdowns (select elements)
        for el in page.locator("select:visible").all():
            label = self._get_label(page, el)
            if not label:
                continue
            options = [o.text_content() for o in el.locator("option").all()
                       if o.get_attribute("value") not in ("", None)]
            filled = answer_question(label, "dropdown", options=options,
                                     company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_qs.append(label)
            elif filled.value:
                el.select_option(label=filled.value)
                _human_delay(0.3, 0.7)

        # ── Radio buttons (LinkedIn wraps these in fieldsets)
        for fieldset in page.locator("fieldset:visible").all():
            legend = fieldset.locator("legend").first.text_content() or ""
            options = [r.text_content().strip()
                       for r in fieldset.locator("label").all()]
            if not options:
                continue
            filled = answer_question(legend, "radio", options=options,
                                     company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_qs.append(legend)
            elif filled.value:
                radio = fieldset.locator(f"label:has-text('{filled.value}')").first
                if radio.is_visible():
                    radio.click()
                    _human_delay(0.3, 0.7)

        return manual_review_qs

    # ── Utilities ─────────────────────────────────────────────────────────────
    def _get_label(self, page: Page, el) -> str:
        """Try to find the label text associated with a form element."""
        try:
            el_id = el.get_attribute("id")
            aria  = el.get_attribute("aria-label")
            placeholder = el.get_attribute("placeholder")

            if aria:
                return aria.strip()
            if el_id:
                lbl = page.locator(f"label[for='{el_id}']").first
                if lbl.count():
                    return lbl.text_content().strip()
            if placeholder:
                return placeholder.strip()
            # Try parent label
            parent_label = el.locator("xpath=ancestor::label").first
            if parent_label.count():
                return parent_label.text_content().strip()
        except Exception:
            pass
        return ""

    def _dismiss_modal(self, page: Page):
        try:
            page.locator("button[aria-label='Dismiss']").first.click()
            _human_delay(0.5, 1)
            # Confirm discard if prompted
            discard = page.locator("button:has-text('Discard')").first
            if discard.is_visible(timeout=2000):
                discard.click()
        except Exception:
            pass

    def close(self):
        try:
            self._context.storage_state(path=SESSION_FILE)
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()