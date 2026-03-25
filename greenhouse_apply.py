"""
greenhouse_apply.py
───────────────────
Automates Greenhouse job application forms using Playwright.

Greenhouse uses a single-page application form at:
    boards.greenhouse.io/<company>/jobs/<job_id>

Form structure (standardised):
    1. Personal info: first name, last name, email, phone
    2. Resume upload
    3. Optional cover letter upload or text area
    4. Custom questions (text, select, radio, checkbox)
    5. Submit button

Notes:
  - No multi-step modal — everything is one page.
  - GDPR consent checkbox may appear depending on company/region.
  - Returns the same ApplyResult interface as linkedin_apply.py.
"""

from __future__ import annotations

import re
import time
import random
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, Page, BrowserContext,
    TimeoutError as PWTimeoutError,
)

from config import RESUME_PATH
from form_filler import answer_question
from navigator import find_button, find_form_fields, find_file_upload
from linkedin_apply import ApplyResult  # reuse same dataclass

SESSION_FILE = Path("output/greenhouse_session.json")
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


class GreenhouseApplyBot:
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
            page.goto(job_url, wait_until="domcontentloaded", timeout=45_000)
            _human_delay(1.5, 3)

            # Greenhouse job pages have a visible Apply button that leads to the form,
            # or the form is embedded directly on the page.
            apply_btn = find_button(page, "apply for this job") or find_button(page, "apply now") or find_button(page, "apply")
            if apply_btn is not None:
                apply_btn.click()
                _human_delay(1.5, 2.5)

            # Wait for the application form to be present
            try:
                page.wait_for_selector("#application-form, form#application, form[id*='application']", timeout=10_000)
            except PWTimeoutError:
                # Form may already be visible on the page
                pass

            _human_delay(0.5, 1)
            result = self._fill_application(page, result)
            self._context.storage_state(path=str(SESSION_FILE))

        except PWTimeoutError as exc:
            result.status = "error"
            result.error_message = f"Timeout: {exc}"
            self._save_debug_snapshot(page, company, title, prefix="greenhouse_timeout")
        except Exception as exc:
            result.status = "error"
            result.error_message = str(exc)
            self._save_debug_snapshot(page, company, title, prefix="greenhouse_exception")

        return result

    def _fill_application(self, page: Page, result: ApplyResult) -> ApplyResult:
        # ── Resume upload ────────────────────────────────────────────────────
        upload_input = find_file_upload(page)
        if upload_input is not None and RESUME_PATH_OBJ.exists():
            try:
                # Only upload if no file is already attached
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

        # ── GDPR / consent checkboxes ────────────────────────────────────────
        self._accept_consent_checkboxes(page)

        # ── Submit ───────────────────────────────────────────────────────────
        submit_btn = (
            find_button(page, "submit application")
            or find_button(page, "submit")
        )
        if submit_btn is None:
            result.status = "error"
            result.error_message = "Submit button not found on Greenhouse form."
            self._save_debug_snapshot(page, result.company, result.title, prefix="greenhouse_no_submit")
            return result

        submit_btn.click()
        _human_delay(2, 4)

        # Confirm submission — Greenhouse redirects to a confirmation page
        if self._is_submitted(page):
            result.status = "applied"
        else:
            # May have inline errors — treat as manual_review
            result.status = "manual_review"
            result.manual_questions.append(
                "Form submission may have failed or requires review. Check the browser."
            )
            self._save_debug_snapshot(page, result.company, result.title, prefix="greenhouse_submit_check")

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

    def _accept_consent_checkboxes(self, page: Page) -> None:
        """Tick any visible GDPR / privacy consent checkboxes that are unchecked."""
        consent_keywords = ["consent", "agree", "privacy", "terms", "gdpr", "acknowledge"]
        for cb in page.locator("input[type='checkbox']:visible").all():
            try:
                if cb.is_checked():
                    continue
                label_text = ""
                cb_id = cb.get_attribute("id") or ""
                if cb_id:
                    lbl = page.locator(f"label[for='{cb_id}']").first
                    if lbl.count() > 0:
                        label_text = (lbl.text_content() or "").lower()
                if not label_text:
                    ancestor = cb.locator("xpath=ancestor::label").first
                    if ancestor.count() > 0:
                        label_text = (ancestor.text_content() or "").lower()
                if any(kw in label_text for kw in consent_keywords):
                    cb.check()
                    _human_delay(0.2, 0.5)
            except Exception:
                continue

    def _is_submitted(self, page: Page) -> bool:
        """Return True if the page looks like a Greenhouse confirmation page."""
        url = page.url.lower()
        if "confirmation" in url or "thank" in url or "success" in url:
            return True
        # Look for confirmation text in the page body
        for phrase in ["application received", "thank you for applying", "successfully submitted", "we'll be in touch"]:
            try:
                if page.locator(f"text={phrase}").count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _save_debug_snapshot(self, page: Page, company: str, title: str, prefix: str = "greenhouse_debug") -> None:
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

    def __enter__(self) -> "GreenhouseApplyBot":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
