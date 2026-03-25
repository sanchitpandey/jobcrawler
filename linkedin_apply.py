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
    locator.fill("")
    locator.type(text, delay=random.randint(35, 90))


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

            result = self._handle_modal(page, result)
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
        return page.locator("button.jobs-apply-button span:has-text('Applied')").count() > 0 or page.locator("text=Applied").count() > 0

    def _find_easy_apply_button(self, page: Page) -> Locator | None:
        selectors = [
            "button.jobs-apply-button",
            "a.jobs-apply-button",
            "button[aria-label*='Easy Apply']",
            "a[aria-label*='Easy Apply']",
            "button:has-text('Easy Apply')",
            "a:has-text('Easy Apply')",
            ".jobs-apply-button--top-card button",
            ".jobs-apply-button--top-card a",
            ".jobs-apply-button button",
            ".jobs-apply-button a",
        ]

        deadline = time.time() + 15
        while time.time() < deadline:
            for selector in selectors:
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                try:
                    if not locator.is_visible():
                        continue
                    label = ((locator.inner_text(timeout=1000) or "") + " " + (locator.get_attribute("aria-label") or "")).lower()
                    if "easy apply" in label:
                        return locator
                except Exception:
                    continue
            _human_delay(0.7, 1.1)
            page.mouse.wheel(0, 250)

        return None

    def _classify_apply_button_failure(self, page: Page, company: str, title: str) -> str:
        self._save_debug_snapshot(page, company, title)

        if page.locator("button:has-text('Apply')").count() > 0 or page.locator("a:has-text('Apply')").count() > 0:
            return "Easy Apply button not found. LinkedIn shows an external Apply flow for this job."
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
        return self._first_visible(page, ["div[role='dialog']", ".artdeco-modal", ".jobs-easy-apply-modal"]) or page

    def _first_visible(self, page, selectors: list[str]) -> Locator | None:
        for selector in selectors:
            try:
                matches = page.locator(selector)
                count = matches.count()
                for idx in range(count):
                    locator = matches.nth(idx)
                    if locator.is_visible():
                        return locator
            except Exception:
                continue
        return None

    def _handle_modal(self, page: Page, result: ApplyResult) -> ApplyResult:
        max_steps = 12

        for step in range(max_steps):
            _human_delay(0.8, 1.8)
            scope = self._get_modal_scope(page)

            submit_btn = self._first_visible(
                scope,
                [
                    "button[aria-label*='Submit application']",
                    "button:has-text('Submit application')",
                    "button:has-text('Submit')",
                ],
            )
            if submit_btn is not None:
                submit_btn.click()
                _human_delay(2, 4)
                result.status = "applied"
                return result

            review_btn = self._first_visible(
                scope,
                [
                    "button[aria-label*='Review']",
                    "button:has-text('Review your application')",
                    "button:has-text('Review')",
                ],
            )
            if review_btn is not None:
                review_btn.click()
                continue

            manual_questions = self._fill_step(scope, result.company, result.title)
            result.manual_questions.extend(manual_questions)
            if manual_questions:
                result.status = "manual_review"
                self._dismiss_modal(page)
                return result

            next_btn = self._first_visible(
                scope,
                [
                    "button[aria-label*='Continue to next step']",
                    "button[aria-label*='Continue']",
                    "button:has-text('Continue to next step')",
                    "button:has-text('Continue')",
                    "button:has-text('Next')",
                    "footer button.artdeco-button--primary",
                    ".artdeco-modal__actionbar button.artdeco-button--primary",
                ],
            )
            if next_btn is not None:
                next_btn.click()
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

    def _fill_step(self, page, company: str, title: str) -> list[str]:
        manual_review_questions: list[str] = []

        upload_input = page.locator("input[type='file']").first
        has_saved_resume_options = self._first_visible(
            page,
            [
                "button[aria-label*='Download resume']",
                "button:has-text('Show more resumes')",
                "button:has-text('Resume')",
            ],
        )
        if has_saved_resume_options is None and upload_input.count() > 0 and upload_input.is_visible() and RESUME_PATH_OBJ.exists():
            try:
                upload_input.set_input_files(str(RESUME_PATH_OBJ))
                _human_delay(1, 2)
            except Exception:
                pass

        for el in page.locator("input[type='text']:visible, textarea:visible").all():
            label = self._get_label(page, el)
            if not label:
                continue
            filled = answer_question(label, "text", company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_questions.append(label)
            elif filled.value and not el.input_value():
                _type_into(el, filled.value)
                _human_delay(0.3, 0.8)

        for el in page.locator("input[type='number']:visible").all():
            label = self._get_label(page, el)
            if not label or el.input_value():
                continue
            filled = answer_question(label, "text", company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_questions.append(label)
            elif filled.value:
                el.fill(re.sub(r"[^\d]", "", filled.value)[:6])
                _human_delay(0.3, 0.6)

        for el in page.locator("select:visible").all():
            label = self._get_label(page, el)
            if not label:
                continue
            options = [
                (option.text_content() or "").strip()
                for option in el.locator("option").all()
                if option.get_attribute("value") not in ("", None)
            ]
            filled = answer_question(label, "dropdown", options=options, company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_questions.append(label)
            elif filled.value:
                el.select_option(label=filled.value)
                _human_delay(0.3, 0.7)

        for fieldset in page.locator("fieldset:visible").all():
            legend = (fieldset.locator("legend").first.text_content() or "").strip()
            options = [(label.text_content() or "").strip() for label in fieldset.locator("label").all()]
            if not legend or not options:
                continue
            filled = answer_question(legend, "radio", options=options, company=company, job_title=title)
            if filled.is_manual_review:
                manual_review_questions.append(legend)
            elif filled.value:
                radio = fieldset.locator(f"label:has-text('{filled.value}')").first
                if radio.count() > 0 and radio.is_visible():
                    radio.click()
                    _human_delay(0.3, 0.7)

        return manual_review_questions

    def _get_label(self, page, el: Locator) -> str:
        try:
            element_id = el.get_attribute("id")
            aria_label = el.get_attribute("aria-label")
            placeholder = el.get_attribute("placeholder")

            if aria_label:
                return aria_label.strip()
            if element_id:
                label = page.locator(f"label[for='{element_id}']").first
                if label.count() > 0:
                    return (label.text_content() or "").strip()
            if placeholder:
                return placeholder.strip()
            parent_label = el.locator("xpath=ancestor::label").first
            if parent_label.count() > 0:
                return (parent_label.text_content() or "").strip()
        except Exception:
            pass
        return ""

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
