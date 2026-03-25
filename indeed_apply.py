"""
indeed_apply.py
───────────────
Automates Indeed Apply using Playwright.

Notes:
  - Indeed has two apply types:
      1. "Apply on Indeed" — handled here (form on Indeed's own UI)
      2. "Apply on company site" — flagged as manual_review (redirects externally)
  - Session is persisted to avoid repeated logins
  - Same ApplyResult / form_filler interface as linkedin_apply.py
"""

from __future__ import annotations
import time, random, json, re
from pathlib import Path
from dataclasses import dataclass, field

from playwright.sync_api import (
    sync_playwright, Page, BrowserContext,
    TimeoutError as PWTimeoutError
)

from form_filler import answer_question
from config import INDEED_EMAIL, INDEED_PASSWORD, RESUME_PATH
from linkedin_apply import ApplyResult   # reuse same dataclass
from navigator import find_button, find_form_fields

SESSION_FILE  = "output/indeed_session.json"
RESUME_PATH_OBJ = Path(RESUME_PATH)


def _human_delay(lo=0.8, hi=2.5):
    time.sleep(random.uniform(lo, hi))


def _slow_type(page: Page, text: str):
    for ch in text:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.04, 0.11))


class IndeedApplyBot:
    def __init__(self, headless: bool = False):
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._load_or_create_context()
        self._page    = self._context.new_page()
        self._page.set_viewport_size({"width": 1280, "height": 900})

    def _load_or_create_context(self) -> BrowserContext:
        session_path = Path(SESSION_FILE)
        ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")
        if session_path.exists():
            return self._browser.new_context(
                storage_state=str(session_path), user_agent=ua)
        return self._browser.new_context(user_agent=ua)

    def login(self) -> bool:
        page = self._page
        page.goto("https://www.indeed.com/account/login", wait_until="networkidle")
        _human_delay(1, 2)

        if page.locator("[data-gnav-element-name='LoggedIn']").count():
            print("  [Indeed] Already logged in.")
            return True

        # Indeed uses email → then either password or OTP
        page.fill("input[type='email'], #ifl-InputFormField-3", INDEED_EMAIL)
        _human_delay(0.5, 1)
        page.keyboard.press("Enter")
        _human_delay(1.5, 2.5)

        # Password step
        pwd_field = page.locator("input[type='password']").first
        if pwd_field.is_visible(timeout=5000):
            pwd_field.fill(INDEED_PASSWORD)
            _human_delay(0.5, 1)
            page.keyboard.press("Enter")
            _human_delay(2, 3)

        # OTP / CAPTCHA
        if page.locator("input[name='otp'], input[autocomplete='one-time-code']").count():
            print("  [Indeed] OTP required — enter it in the browser window, then press Enter here.")
            input()

        self._context.storage_state(path=SESSION_FILE)
        print("  [Indeed] ✓ Logged in.")
        return True

    def apply(
        self,
        job_url:   str,
        company:   str = "",
        title:     str = "",
    ) -> ApplyResult:
        page   = self._page
        result = ApplyResult(status="error", job_url=job_url, company=company, title=title)

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=30_000)
            _human_delay(1.5, 3)

            # Detect external apply (company site)
            if find_button(page, "apply on company site") is not None:
                result.status = "manual_review"
                result.manual_questions = ["External company site — must apply manually"]
                return result

            # Detect "Applied" badge
            if find_button(page, "applied") is not None:
                result.status = "already_applied"
                return result

            # Click "Apply now" (Indeed's own form)
            apply_btn = find_button(page, "apply now")
            if apply_btn is None:
                result.status = "error"
                result.error_message = "No Apply button found"
                return result

            apply_btn.click()
            _human_delay(1.5, 3)

            # Indeed opens a new tab or an iframe modal
            # Handle new tab case
            if len(page.context.pages) > 1:
                page = page.context.pages[-1]
                self._page = page
                _human_delay(1, 2)

            result = self._handle_indeed_form(page, result)
            self._context.storage_state(path=SESSION_FILE)

        except PWTimeoutError as e:
            result.status = "error"
            result.error_message = f"Timeout: {e}"
        except Exception as e:
            result.status = "error"
            result.error_message = str(e)

        return result

    def _handle_indeed_form(self, page: Page, result: ApplyResult) -> ApplyResult:
        MAX_STEPS = 10

        for step in range(MAX_STEPS):
            _human_delay(1, 2)

            # Upload resume if prompted
            resume_input = page.locator("input[type='file']").first
            if resume_input.is_visible(timeout=2000) and RESUME_PATH_OBJ.exists():
                resume_input.set_input_files(str(RESUME_PATH_OBJ))
                _human_delay(1.5, 2.5)

            # Check for submit
            submit_btn = find_button(page, "submit your application")
            if submit_btn is not None:
                submit_btn.click()
                _human_delay(2, 4)
                result.status = "applied"
                return result

            # Fill current page's questions
            manual_qs = self._fill_page(page, result.company, result.title)
            result.manual_questions.extend(manual_qs)

            if manual_qs:
                result.status = "manual_review"
                return result

            # Next / Continue button
            next_btn = find_button(page, "continue") or find_button(page, "next")
            if next_btn is not None:
                next_btn.click()
            else:
                result.status = "error"
                result.error_message = f"Stuck on step {step}"
                return result

        result.status = "error"
        result.error_message = "Exceeded max steps"
        return result

    def _fill_page(self, page: Page, company: str, title: str) -> list[str]:
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
                    field.locator.click()
                    _slow_type(page, filled.value)
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
                    field.locator.fill(re.sub(r"[^\d]", "", filled.value)[:6])
                    _human_delay(0.3, 0.6)

            elif field.field_type == "select":
                filled = answer_question(label, "dropdown", options=field.options,
                                         company=company, job_title=title)
                if filled.is_manual_review:
                    manual.append(label)
                elif filled.value:
                    try:
                        field.locator.select_option(label=filled.value)
                    except Exception:
                        pass
                    _human_delay(0.3, 0.7)

            elif field.field_type == "radio":
                filled = answer_question(label, "radio", options=field.options,
                                         company=company, job_title=title)
                if filled.is_manual_review:
                    manual.append(label)
                elif filled.value:
                    group = page.locator("fieldset:visible, [role='radiogroup']:visible").filter(has_text=label)
                    if group.count() > 0:
                        radio_btn = group.first.locator("label").filter(has_text=filled.value).first
                        if radio_btn.count() > 0 and radio_btn.is_visible():
                            radio_btn.click()
                            _human_delay(0.3, 0.7)

        return manual

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