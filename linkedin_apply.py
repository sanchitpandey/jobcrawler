"""LinkedIn Easy Apply automation using Playwright."""

from __future__ import annotations

import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import BrowserContext, Locator, Page, TimeoutError as PWTimeoutError, sync_playwright

from config import LINKEDIN_EMAIL, LINKEDIN_PASSWORD, RESUME_PATH
from form_filler import answer_question
from navigator import find_button, find_form_fields, find_modal
from checkpoint import save_checkpoint, load_checkpoint, clear_checkpoint

SESSION_FILE = Path("output/linkedin_session.json")
RESUME_PATH_OBJ = Path(RESUME_PATH)
DEBUG_DIR = Path("output/debug")


@dataclass
class ApplyResult:
    status: str
    job_url: str = ""
    company: str = ""
    title: str = ""
    manual_questions: list[str] = field(default_factory=list)
    error_message: str = ""


def _human_delay(lo: float = 0.8, hi: float = 2.5) -> None:
    time.sleep(random.uniform(lo, hi))


def _sanitize_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower())
    return cleaned.strip("_") or "job"


def _type_into(locator: Locator, text: str) -> None:
    locator.click()
    locator.fill(text)
    _human_delay(0.1, 0.3)


def _wait_for_page_ready(page: Page, selectors: list[str] | None = None, timeout_ms: int = 15000) -> None:
    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_load_state("load", timeout=min(timeout_ms, 10000))
    except PWTimeoutError:
        pass

    if selectors:
        deadline = time.time() + (timeout_ms / 1000)
        while time.time() < deadline:
            for selector in selectors:
                try:
                    if page.locator(selector).count() > 0:
                        return
                except Exception:
                    continue
            time.sleep(0.25)


class LinkedInApplyBot:
    def __init__(self, headless: bool = False):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = self._load_or_create_context()
        self._page = self._context.new_page()
        self._page.set_viewport_size({"width": 1440, "height": 1100})
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    def _load_or_create_context(self) -> BrowserContext:
        common_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }
        if SESSION_FILE.exists():
            return self._browser.new_context(storage_state=str(SESSION_FILE), **common_kwargs)
        return self._browser.new_context(**common_kwargs)

    def login(self) -> bool:
        page = self._page
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        _wait_for_page_ready(page, selectors=["#username", ".global-nav", "nav"], timeout_ms=15000)
        _human_delay()

        if "feed" in page.url or page.locator(".global-nav").count() > 0:
            print("  [LinkedIn] Already logged in.")
            return True

        if not LINKEDIN_EMAIL or not LINKEDIN_PASSWORD:
            print("  [LinkedIn] Login failed. LINKEDIN_EMAIL or LINKEDIN_PASSWORD is missing.")
            return False

        page.fill("#username", LINKEDIN_EMAIL)
        _human_delay(0.3, 0.8)
        page.fill("#password", LINKEDIN_PASSWORD)
        _human_delay(0.5, 1.2)
        page.click('[data-litms-control-urn="login-submit"]')
        page.wait_for_load_state("networkidle")
        _human_delay(2, 4)

        if "checkpoint" in page.url or "captcha" in page.url.lower():
            print("  [LinkedIn] CAPTCHA or checkpoint detected. Solve it manually, then press Enter.")
            input()
            _wait_for_page_ready(page, selectors=[".global-nav", "nav"], timeout_ms=15000)

        if "feed" in page.url or page.locator(".global-nav").count() > 0:
            self._context.storage_state(path=str(SESSION_FILE))
            print("  [LinkedIn] Logged in and session saved.")
            return True

        print("  [LinkedIn] Login failed. Check LINKEDIN_EMAIL and LINKEDIN_PASSWORD.")
        return False

    def _detect_redirected_away(self, page: Page, job_url: str) -> str | None:
        """Return an error message if LinkedIn redirected away from the target job page.

        Returns None if we appear to be on the correct job detail page.
        """
        # Extract expected job ID from the original URL
        m = re.search(r"/view/(\d+)", job_url)
        expected_id = m.group(1) if m else None

        page_title = ""
        try:
            page_title = page.title()
        except Exception:
            pass

        current_url = page.url

        # LinkedIn "Similar Jobs" redirect — the listing expired and LinkedIn shows alternatives
        if "similar jobs" in page_title.lower():
            return (
                "Job listing no longer available — LinkedIn redirected to 'Similar Jobs' page. "
                "The posting has likely expired or been removed."
            )

        # If the URL no longer contains the expected job ID, we may be on the wrong page
        if expected_id and expected_id not in current_url:
            # Only flag this if we also see search-results indicators (not just a normal redirect)
            try:
                if page.locator(".jobs-search-results-list, .jobs-search-results__list").count() > 0:
                    return (
                        f"Job listing no longer available — navigated to job {expected_id} "
                        f"but landed on a search/listing page ({current_url[:80]})."
                    )
            except Exception:
                pass

        return None

    def apply(self, job_url: str, company: str = "", title: str = "") -> ApplyResult:
        page = self._page
        result = ApplyResult(status="error", job_url=job_url, company=company, title=title)

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=45_000)
            _wait_for_page_ready(
                page,
                selectors=[
                    ".jobs-details",
                    ".jobs-search__job-details--container",
                    ".jobs-unified-top-card",
                    "button.jobs-apply-button",
                    "main",
                ],
                timeout_ms=20000,
            )
            _human_delay(2, 4)
            self._prepare_job_page(page)

            # Detect if LinkedIn redirected away from the target job (e.g. expired listing)
            redirect_msg = self._detect_redirected_away(page, job_url)
            if redirect_msg:
                result.status = "error"
                result.error_message = redirect_msg
                print(f"  [LinkedIn] {redirect_msg}")
                return result

            if self._is_already_applied(page):
                result.status = "already_applied"
                return result

            easy_apply_btn = self._find_easy_apply_button(page)
            if easy_apply_btn is None:
                failure_message = self._classify_apply_button_failure(page, company, title)
                if "external apply" in failure_message.lower():
                    result.status = "manual_review"
                    result.manual_questions.append(failure_message)
                else:
                    result.status = "error"
                    result.error_message = failure_message
                return result

            apply_href = ""
            tag_name = ""
            try:
                apply_href = easy_apply_btn.get_attribute("href") or ""
            except Exception:
                pass
            try:
                tag_name = (easy_apply_btn.evaluate("(el) => el.tagName") or "").lower()
            except Exception:
                pass

            if tag_name == "a" and apply_href and "/apply/" in apply_href:
                page.goto(urljoin("https://www.linkedin.com", apply_href), wait_until="domcontentloaded", timeout=45_000)
                _human_delay(1, 2)
            else:
                easy_apply_btn.click()
                _human_delay(1, 2)

            if not self._wait_for_apply_surface(page):
                if apply_href:
                    page.goto(urljoin("https://www.linkedin.com", apply_href), wait_until="domcontentloaded", timeout=45_000)
                    _human_delay(1, 2)

            if not self._wait_for_apply_surface(page):
                result.status = "error"
                result.error_message = (
                    "Easy Apply was clicked, but LinkedIn did not open the application form. "
                    "Debug snapshot saved under output/debug/."
                )
                self._save_debug_snapshot(page, company, title, prefix="linkedin_apply_surface_missing")
                return result

            cp_id = _sanitize_slug(job_url)
            checkpoint = load_checkpoint(cp_id)
            start_step = checkpoint["step"] if checkpoint else 0
            result = self._handle_modal(page, result, cp_id=cp_id, start_step=start_step)
            self._context.storage_state(path=str(SESSION_FILE))
        except PWTimeoutError as exc:
            result.status = "error"
            result.error_message = f"Timeout while loading or applying: {exc}"
            self._save_debug_snapshot(page, company, title, prefix="linkedin_timeout")
        except Exception as exc:
            result.status = "error"
            result.error_message = str(exc)
            self._save_debug_snapshot(page, company, title, prefix="linkedin_exception")

        return result

    def _prepare_job_page(self, page: Page) -> None:
        page.mouse.wheel(0, 700)
        _human_delay(0.5, 1.0)
        page.mouse.wheel(0, -700)
        _human_delay(0.5, 1.0)
        for selector in [
            ".jobs-details",
            ".jobs-search__job-details--container",
            ".jobs-unified-top-card",
            "button.jobs-apply-button",
        ]:
            if page.locator(selector).count() > 0:
                break
        _human_delay(0.5, 1.2)

    def _is_already_applied(self, page: Page) -> bool:
        """Return True only when the apply button itself signals already-applied.

        Deliberately avoids broad page-text matches like "100 people applied"
        or sidebar "Applied X days ago" that appear on external-link jobs.
        """
        try:
            # LinkedIn's own confirmation banner
            if page.locator("text='You applied'").count() > 0:
                return True

            # The specific apply button with text "Applied" or aria-label containing "Applied"
            apply_btn = page.locator("button.jobs-apply-button").first
            if apply_btn.count() > 0:
                try:
                    text = (apply_btn.inner_text(timeout=500) or "").strip().lower()
                    if text == "applied":
                        return True
                    aria = (apply_btn.get_attribute("aria-label") or "").lower()
                    if "applied" in aria and "easy apply" not in aria:
                        return True
                except Exception:
                    pass

            # Disabled apply button that explicitly says Applied
            if page.locator("button.jobs-apply-button:disabled:has-text('Applied')").count() > 0:
                return True
        except Exception:
            pass
        return False

    def _find_easy_apply_button(self, page: Page) -> Locator | None:
        card = page.locator(".jobs-unified-top-card, .job-view-layout").first
        scope = card if card.count() > 0 else page

        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                btn = scope.locator("button.jobs-apply-button:has-text('Easy Apply')").first
                if btn.count() > 0 and btn.bounding_box():
                    return btn
                
                for el in scope.locator("button, [role='button']").all():
                    if el.bounding_box():
                        text = (el.inner_text(timeout=500) or "").strip().lower()
                        if text == "easy apply":
                            return el
            except Exception:
                pass
                
            btn = find_button(scope if card.count() > 0 else page, "easy apply")
            if btn is not None:
                try:
                    text = (btn.inner_text(timeout=500) or "").strip().lower()
                    if "easy" in text:
                        return btn
                except Exception:
                    pass
            _human_delay(0.7, 1.1)
            page.mouse.wheel(0, 250)
        return None

    def _classify_apply_button_failure(self, page: Page, company: str, title: str) -> str:
        self._save_debug_snapshot(page, company, title)

        ext_btn = page.locator("button:has-text('Apply'), a:has-text('Apply')").first
        if ext_btn.count() > 0:
            href = ""
            try:
                href = ext_btn.get_attribute("href") or ""
            except Exception:
                pass
            url_suffix = f" | external_apply_url:{href}" if href else ""
            return f"Easy Apply button not found. LinkedIn shows an external Apply flow for this job.{url_suffix}"
        if "login" in page.url or page.locator("#username").count() > 0:
            return "LinkedIn session was not active on the job page."
        if page.locator("text=Sign in to see more jobs").count() > 0:
            return "LinkedIn redirected to a logged-out job view."
        return "Easy Apply button not found on the loaded LinkedIn job page. Debug snapshot saved under output/debug/."

    def _save_debug_snapshot(self, page: Page, company: str, title: str, prefix: str = "linkedin_debug") -> None:
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

    def _wait_for_apply_surface(self, page: Page, timeout_seconds: float = 8.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if "/apply/" in page.url or "openSDUIApplyFlow=true" in page.url:
                return True
            for selector in [
                "div[role='dialog']",
                ".artdeco-modal",
                ".jobs-easy-apply-modal",
                "div[role='dialog'] input[type='file']",
                "div[role='dialog'] button",
                ".artdeco-modal__actionbar button",
            ]:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        return True
                except Exception:
                    continue
            _human_delay(0.4, 0.8)
        return False

    def _get_modal_scope(self, page: Page):
        return find_modal(page) or page

    def _handle_modal(
        self,
        page: Page,
        result: ApplyResult,
        cp_id: str = "",
        start_step: int = 0,
    ) -> ApplyResult:
        max_steps = 12
        all_filled: dict[str, str] = {}
        error_streak = 0  # consecutive iterations where form errors were detected

        for step in range(max_steps):
            _human_delay(0.8, 1.8)
            print(f"DEBUG: --- Starting Modal Step {step} (error_streak={error_streak}) ---")
            try:
                page.screenshot(path=f"output/debug/loop_step_{step}.png")
            except Exception:
                pass

            scope = self._get_modal_scope(page)

            submit_btn = find_button(scope, "submit application")
            if submit_btn is not None:
                submit_btn.click()
                result.status = "applied"
                return result

            # Steps already completed in a previous run: advance without re-filling
            if step < start_step:
                next_btn = find_button(scope, "continue to next step") or find_button(scope, "next")
                if next_btn is not None:
                    next_btn.click()
                    continue

                review_btn = find_button(scope, "review your application")
                if review_btn is not None:
                    review_btn.click()
                    continue

            manual_questions, step_filled, has_error = self._fill_step(scope, result.company, result.title)
            all_filled.update(step_filled)
            result.manual_questions.extend(manual_questions)

            if manual_questions:
                result.status = "manual_review"
                self._dismiss_modal(page)
                return result

            if has_error:
                error_streak += 1
                if error_streak >= 3:
                    # Stuck on the same validation error after 3 attempts — flag for manual review
                    result.status = "manual_review"
                    result.manual_questions.append(
                        f"Validation error on modal step {step + 1} persisted after {error_streak} retries — needs manual review."
                    )
                    self._dismiss_modal(page)
                    return result
                # Try to fix the invalid field(s) and retry the same form state
                self._fix_validation_errors(scope, result.company, result.title)
                continue  # Re-run _fill_step on the same modal without clicking Next

            error_streak = 0  # no errors this iteration — reset streak

            # Click next or review AFTER fields are filled
            next_btn = find_button(scope, "continue to next step") or find_button(scope, "next")
            review_btn = find_button(scope, "review your application")

            if next_btn is not None:
                next_btn.click()
                if cp_id:
                    save_checkpoint(cp_id, step + 1, all_filled)
                continue
            elif review_btn is not None:
                review_btn.click()
                if cp_id:
                    save_checkpoint(cp_id, step + 1, all_filled)
                continue

            result.status = "error"
            self._save_debug_snapshot(page, result.company, result.title, prefix="linkedin_modal_stuck")
            result.error_message = (
                f"Stuck on modal step {step + 1}. No Next, Review, or Submit button was visible. "
                "Debug snapshot saved under output/debug/."
            )
            self._dismiss_modal(page)
            return result

        result.status = "error"
        result.error_message = "Exceeded maximum Easy Apply modal steps."
        self._dismiss_modal(page)
        return result

    def _fill_step(
        self, page, company: str, title: str
    ) -> tuple[list[str], dict[str, str], bool]:
        manual_review_questions: list[str] = []
        filled_values: dict[str, str] = {}

        # File upload — handled outside find_form_fields since it's not a question field
        upload_input = page.locator("input[type='file']").first
        has_saved_resume = find_button(page, "resume")
        if has_saved_resume is None and upload_input.count() > 0 and upload_input.is_visible() and RESUME_PATH_OBJ.exists():
            try:
                upload_input.set_input_files(str(RESUME_PATH_OBJ))
                _human_delay(1, 2)
            except Exception:
                pass

        for field in find_form_fields(page):
            label = field.label
            if not label:
                continue
            
            print(f"DEBUG: Found field '{label}' (type: {field.field_type})")

            if field.field_type in ("text", "email", "tel", "textarea"):
                try:
                    if field.locator.input_value():
                        print(f"DEBUG: Field '{label}' already has value: {field.locator.input_value()}")
                        continue
                except Exception:
                    pass
                filled = answer_question(label, "text", company=company, job_title=title)
                print(f"DEBUG: Answer for '{label}': {filled}")
                if filled.is_manual_review:
                    manual_review_questions.append(label)
                elif filled.value:
                    # Strip non-digits for text fields that actually expect a number
                    # (LinkedIn uses type="text" for some numeric fields with validation)
                    answer_text = filled.value
                    if re.search(r"\byrs?\b.*exp|\byears?\b.*exp|years? of exp", label, re.I):
                        digits_only = re.sub(r"[^\d]", "", answer_text)
                        if digits_only:
                            answer_text = digits_only
                    _type_into(field.locator, answer_text)
                    filled_values[label] = answer_text
                    _human_delay(0.3, 0.8)

            elif field.field_type == "number":
                try:
                    if field.locator.input_value():
                        print(f"DEBUG: Field '{label}' already has value: {field.locator.input_value()}")
                        continue
                except Exception:
                    pass
                filled = answer_question(label, "text", company=company, job_title=title)
                print(f"DEBUG: Answer for '{label}': {filled}")
                if filled.is_manual_review:
                    manual_review_questions.append(label)
                elif filled.value:
                    digits = re.sub(r"[^\d]", "", filled.value)[:6]
                    field.locator.fill(digits)
                    filled_values[label] = digits
                    _human_delay(0.3, 0.6)

            elif field.field_type == "select":
                filled = answer_question(label, "dropdown", options=field.options, company=company, job_title=title)
                print(f"DEBUG: Answer for '{label}': {filled}")
                if filled.is_manual_review:
                    manual_review_questions.append(label)
                elif filled.value:
                    field.locator.select_option(label=filled.value)
                    filled_values[label] = filled.value
                    _human_delay(0.3, 0.7)

            elif field.field_type == "radio":
                filled = answer_question(label, "radio", options=field.options, company=company, job_title=title)
                print(f"DEBUG: Answer for '{label}': {filled}")
                if filled.is_manual_review:
                    manual_review_questions.append(label)
                elif filled.value:
                    group = page.locator("fieldset:visible, [role='radiogroup']:visible").filter(has_text=label)
                    if group.count() > 0:
                        radio_btn = group.first.locator("label").filter(has_text=filled.value).first
                        if radio_btn.count() > 0 and radio_btn.is_visible():
                            radio_btn.click()
                            filled_values[label] = filled.value
                            _human_delay(0.3, 0.7)

        # Check for error text in the modal
        error_locators = page.locator(".artdeco-inline-feedback--error")
        has_error = False
        if error_locators.count() > 0:
            for i in range(error_locators.count()):
                err_text = error_locators.nth(i).inner_text().strip()
                if err_text:
                    has_error = True
                    print(f"DEBUG: Form error visible: {err_text}")

        return manual_review_questions, filled_values, has_error

    def _fix_validation_errors(self, scope, company: str, title: str) -> bool:
        """Find aria-invalid fields, clear them, and re-answer. Returns True if at least one field was touched."""
        touched = False
        try:
            invalid_fields = scope.locator("[aria-invalid='true']").all()
            for field_loc in invalid_fields:
                try:
                    # Derive label from aria-label, placeholder, or associated <label>
                    label = (field_loc.get_attribute("aria-label") or "").strip()
                    if not label:
                        label = (field_loc.get_attribute("placeholder") or "").strip()
                    if not label:
                        field_id = field_loc.get_attribute("id") or ""
                        if field_id:
                            lbl_el = scope.locator(f"label[for='{field_id}']")
                            if lbl_el.count() > 0:
                                label = (lbl_el.inner_text(timeout=500) or "").strip()
                    if not label:
                        continue

                    field_loc.click()
                    field_loc.fill("")
                    _human_delay(0.2, 0.4)

                    filled = answer_question(label, "number", company=company, job_title=title)
                    if filled.value:
                        digits = re.sub(r"[^\d.]", "", filled.value)
                        field_loc.fill(digits if digits else filled.value)
                        _human_delay(0.2, 0.4)
                        touched = True
                except Exception:
                    continue
        except Exception:
            pass
        return touched

    def _dismiss_modal(self, page: Page) -> None:
        try:
            dismiss = page.locator("button[aria-label='Dismiss'], button[aria-label='Dismiss application']").first
            if dismiss.count() > 0 and dismiss.is_visible():
                dismiss.click()
                _human_delay(0.5, 1)
            discard = page.locator("button:has-text('Discard')").first
            if discard.count() > 0 and discard.is_visible():
                discard.click()
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

    def __enter__(self) -> "LinkedInApplyBot":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
