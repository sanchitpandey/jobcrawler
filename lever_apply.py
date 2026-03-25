"""
lever_apply.py
──────────────
Automates Lever job application forms using Playwright.

Lever uses a single-page application form at:
    jobs.lever.co/<company>/<uuid>/apply

Form structure (standardised):
    1. Personal info: full name, email, phone, company, LinkedIn, GitHub, portfolio
    2. Resume upload (drag-and-drop area with hidden file input)
    3. Cover letter (optional textarea or file upload)
    4. Custom questions (text, select, radio)
    5. Submit button

Notes:
  - No multi-step modal — everything is one page.
  - The /apply suffix navigates directly to the application form.
  - If the URL lacks /apply, the bot tries to find and click the Apply button.
  - Returns the same ApplyResult interface as linkedin_apply.py.
"""

from __future__ import annotations

import re
import time
import random
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, Page, BrowserContext,
    TimeoutError as PWTimeoutError,
)

from config import RESUME_PATH
from form_filler import answer_question
from navigator import find_button, find_form_fields, find_file_upload
from linkedin_apply import ApplyResult  # reuse same dataclass

SESSION_FILE = Path("output/lever_session.json")
RESUME_PATH_OBJ = Path(RESUME_PATH)
DEBUG_DIR = Path("output/debug")


def _human_delay(lo: float = 0.8, hi: float = 2.5) -> None:
    time.sleep(random.uniform(lo, hi))


def _type_into(locator, text: str) -> None:
    locator.click()
    locator.fill("")
    locator.type(text, delay=random.randint(35, 90))


def _sanitize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return cleaned.strip("_") or "job"


def _ensure_apply_url(url: str) -> str:
    """Append /apply if the Lever URL is the job detail page, not the form."""
    url = url.rstrip("/")
    if not url.endswith("/apply"):
        url = f"{url}/apply"
    return url


class LeverApplyBot:
    def __init__(self, headless: bool = False):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._load_or_create_context()
        self._page = self._context.new_page()
        self._page.set_viewport_size({"width": 1280, "height": 900})
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    def _load_or_create_context(self) -> BrowserContext:
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
        if SESSION_FILE.exists():
            return self._browser.new_context(
                storage_state=str(SESSION_FILE), user_agent=ua
            )
        return self._browser.new_context(user_agent=ua)

    def apply(
        self,
        job_url: str,
        company: str = "",
        title: str = "",
    ) -> ApplyResult:
        page = self._page
        result = ApplyResult(status="error", job_url=job_url, company=company, title=title)

        try:
            # Navigate directly to the apply form page
            apply_url = _ensure_apply_url(job_url)
            page.goto(apply_url, wait_until="domcontentloaded", timeout=45_000)
            _human_delay(1.5, 3)

            # If /apply URL redirected back to job detail, click the Apply button
            if "/apply" not in page.url:
                apply_btn = find_button(page, "apply for this job") or find_button(page, "apply")
                if apply_btn is not None:
                    apply_btn.click()
                    _human_delay(1.5, 2.5)
                else:
                    result.status = "error"
                    result.error_message = "Could not find Apply button on Lever job page."
                    self._save_debug_snapshot(page, company, title, prefix="lever_no_apply_btn")
                    return result

            # Wait for the application form
            try:
                page.wait_for_selector(
                    "form.application-form, form[data-qa='application-form'], .application-form",
                    timeout=10_000,
                )
            except PWTimeoutError:
                pass

            _human_delay(0.5, 1)
            result = self._fill_application(page, result)
            self._context.storage_state(path=str(SESSION_FILE))

        except PWTimeoutError as exc:
            result.status = "error"
            result.error_message = f"Timeout: {exc}"
            self._save_debug_snapshot(page, company, title, prefix="lever_timeout")
        except Exception as exc:
            result.status = "error"
            result.error_message = str(exc)
            self._save_debug_snapshot(page, company, title, prefix="lever_exception")

        return result

    def _fill_application(self, page: Page, result: ApplyResult) -> ApplyResult:
        # ── Resume upload ────────────────────────────────────────────────────
        # Lever wraps its file input in a drag-drop zone; the input is hidden
        # but set_input_files works without visibility.
        upload_input = page.locator("input[type='file']").first
        if upload_input.count() > 0 and RESUME_PATH_OBJ.exists():
            try:
                current_val = upload_input.input_value() if upload_input.count() > 0 else ""
                if not current_val:
                    upload_input.set_input_files(str(RESUME_PATH_OBJ))
                    _human_delay(1, 2)
            except Exception:
                pass

        # ── Form fields ──────────────────────────────────────────────────────
        manual_questions = self._fill_fields(page, result.company, result.title)
        result.manual_questions.extend(manual_questions)
        if manual_questions:
            result.status = "manual_review"
            return result

        # ── Submit ───────────────────────────────────────────────────────────
        submit_btn = (
            find_button(page, "submit application")
            or find_button(page, "submit")
            or find_button(page, "send application")
        )
        if submit_btn is None:
            result.status = "error"
            result.error_message = "Submit button not found on Lever form."
            self._save_debug_snapshot(page, result.company, result.title, prefix="lever_no_submit")
            return result

        submit_btn.click()
        _human_delay(2, 4)

        # Confirm submission — Lever redirects to a thank-you page
        if self._is_submitted(page):
            result.status = "applied"
        else:
            result.status = "manual_review"
            result.manual_questions.append(
                "Form submission may have failed or requires review. Check the browser."
            )
            self._save_debug_snapshot(page, result.company, result.title, prefix="lever_submit_check")

        return result

    def _fill_fields(self, page: Page, company: str, title: str) -> list[str]:
        manual: list[str] = []

        for field in find_form_fields(page):
            label = field.label
            if not label:
                continue

            if field.field_type in ("text", "email", "tel", "textarea"):
                try:
                    if field.locator.input_value():
                        continue
                except Exception:
                    pass
                filled = answer_question(label, "text", company=company, job_title=title)
                if filled.is_manual_review:
                    manual.append(label)
                elif filled.value:
                    _type_into(field.locator, filled.value)
                    _human_delay(0.3, 0.7)

            elif field.field_type == "number":
                try:
                    if field.locator.input_value():
                        continue
                except Exception:
                    pass
                filled = answer_question(label, "text", company=company, job_title=title)
                if filled.is_manual_review:
                    manual.append(label)
                elif filled.value:
                    digits = re.sub(r"[^\d]", "", filled.value)[:6]
                    field.locator.fill(digits)
                    _human_delay(0.3, 0.6)

            elif field.field_type == "select":
                filled = answer_question(
                    label, "dropdown", options=field.options, company=company, job_title=title
                )
                if filled.is_manual_review:
                    manual.append(label)
                elif filled.value:
                    try:
                        field.locator.select_option(label=filled.value)
                    except Exception:
                        pass
                    _human_delay(0.3, 0.7)

            elif field.field_type == "radio":
                filled = answer_question(
                    label, "radio", options=field.options, company=company, job_title=title
                )
                if filled.is_manual_review:
                    manual.append(label)
                elif filled.value:
                    group = page.locator(
                        "[role='radiogroup']:visible, fieldset:visible"
                    ).filter(has_text=label)
                    if group.count() > 0:
                        radio_btn = group.first.locator("label").filter(has_text=filled.value).first
                        if radio_btn.count() > 0 and radio_btn.is_visible():
                            radio_btn.click()
                            _human_delay(0.3, 0.7)

        return manual

    def _is_submitted(self, page: Page) -> bool:
        """Return True if the page looks like a Lever confirmation page."""
        url = page.url.lower()
        if "confirmation" in url or "thank" in url or "success" in url:
            return True
        for phrase in [
            "application submitted",
            "thank you for applying",
            "application received",
            "we'll be in touch",
            "successfully submitted",
        ]:
            try:
                if page.locator(f"text={phrase}").count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _save_debug_snapshot(self, page: Page, company: str, title: str, prefix: str = "lever_debug") -> None:
        slug = _sanitize_slug(f"{company}_{title}")[:80]
        screenshot_path = DEBUG_DIR / f"{prefix}_{slug}.png"
        html_path = DEBUG_DIR / f"{prefix}_{slug}.html"
        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass
        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._context.storage_state(path=str(SESSION_FILE))
        except Exception:
            pass
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    def __enter__(self) -> "LeverApplyBot":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
