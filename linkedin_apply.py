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


def _enforce_maxlength(locator: Locator, text: str) -> str:
    """Truncate *text* to the field's maxlength attribute (at a word boundary if possible)."""
    try:
        ml = locator.get_attribute("maxlength")
        if ml and ml.isdigit():
            limit = int(ml)
            if len(text) > limit:
                truncated = text[:limit]
                # Back up to last word boundary to avoid cutting mid-word
                boundary = truncated.rsplit(" ", 1)[0].rstrip(".,;: ")
                return boundary if boundary else truncated[:limit]
    except Exception:
        pass
    return text


def _parse_char_limit_from_error(error_text: str) -> int | None:
    """Extract character limit from LinkedIn's validation message, e.g. 'Please enter 300 characters or fewer'."""
    m = re.search(r"(\d+)\s+characters?\s+or\s+fewer", error_text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"maximum\s+(\d+)\s+characters?", error_text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"must\s+be\s+(\d+)\s+characters?\s+or\s+(less|fewer)", error_text, re.I)
    if m:
        return int(m.group(1))
    return None


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

        Key distinction:
          - A REAL "Similar Jobs" redirect: the whole page is a job-search/collection page,
            the URL changes, and the job card (.jobs-unified-top-card) is absent.
          - A normal job detail page: may have a "Similar jobs" recommendation SECTION at the
            bottom, but the top card is present and the URL still contains the job ID.
        We only flag the former.  We deliberately avoid h2/h3 text checks and .jobs-similar-jobs
        CSS class checks because those match the bottom recommendation section on real job pages.
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

        # 1. Page title is the most reliable early signal when LinkedIn fully redirects.
        #    The title "Similar Jobs" or "Jobs | LinkedIn" (generic) combined with other checks.
        if "similar jobs" in page_title.lower():
            # Debug: save screenshot so we can see what LinkedIn is actually showing.
            try:
                slug = _sanitize_slug(expected_id or "unknown")
                page.screenshot(path=str(DEBUG_DIR / f"redirect_debug_{slug}.png"), full_page=False)
            except Exception:
                pass
            print(f"  [DEBUG redirect] title={page_title!r}  url={current_url[:120]}")
            return (
                "Job listing no longer available — LinkedIn redirected to 'Similar Jobs' page. "
                "The posting has likely expired or been removed."
            )

        # 2. URL-based redirect detection: the URL changed to a search/collection page.
        redirect_url_patterns = [
            "similarJobs=true",
            "/jobs/collections/",
            "/jobs/search/",
        ]
        for pattern in redirect_url_patterns:
            if pattern in current_url:
                return (
                    "Job listing no longer available — LinkedIn redirected to a job search page. "
                    "The posting has likely expired or been removed."
                )

        # 3. Job ID missing from URL + top card absent = we're on the wrong page entirely.
        #    (We check the top card because on a real job page it is always present.)
        if expected_id and expected_id not in current_url:
            try:
                top_card_present = page.locator(".jobs-unified-top-card, .job-view-layout").count() > 0
                if not top_card_present:
                    # No job card AND URL doesn't have the job ID → redirected away
                    return (
                        f"Job listing no longer available — navigated to job {expected_id} "
                        f"but the job detail card is absent ({current_url[:80]})."
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
            # LinkedIn's own confirmation banners
            for banner_text in ("You applied", "Application submitted"):
                if page.locator(f"text='{banner_text}'").count() > 0:
                    return True

            # Check page-level banners/notifications scoped to the job card area
            for selector in [
                ".jobs-details-top-card__apply-error",
                ".artdeco-inline-feedback",
                ".jobs-s-apply",
            ]:
                try:
                    el = page.locator(selector).first
                    if el.count() > 0:
                        text = (el.inner_text(timeout=500) or "").lower()
                        if "application submitted" in text or "you applied" in text:
                            return True
                except Exception:
                    pass

            # The specific apply button with text "Applied"/"Application submitted"
            # or aria-label indicating already applied
            apply_btn = page.locator("button.jobs-apply-button").first
            if apply_btn.count() > 0:
                try:
                    text = (apply_btn.inner_text(timeout=500) or "").strip().lower()
                    if text in ("applied", "application submitted"):
                        return True
                    aria = (apply_btn.get_attribute("aria-label") or "").lower()
                    if ("applied" in aria or "submitted" in aria) and "easy apply" not in aria:
                        return True
                except Exception:
                    pass

            # Disabled apply button that says Applied or Application submitted
            if page.locator("button.jobs-apply-button:disabled:has-text('Applied')").count() > 0:
                return True
            if page.locator("button.jobs-apply-button:disabled:has-text('Application submitted')").count() > 0:
                return True
        except Exception:
            pass
        return False

    def _find_easy_apply_button(self, page: Page) -> Locator | None:
        """Find the Easy Apply button on the job detail page.

        LinkedIn's new design uses obfuscated CSS classes, so we rely exclusively on
        aria-label and text content.  The old .jobs-unified-top-card / .jobs-apply-button
        class selectors no longer exist.

        To avoid picking up "Easy Apply" links from the "Similar jobs" recommendation
        section at the bottom of the page, we scroll back to the top each iteration and
        only bail on URL-pattern changes (not heading text).
        """
        deadline = time.time() + 15

        while time.time() < deadline:
            # Safety net: if the SPA redirected away (URL changed to search/collections), bail fast.
            # We do NOT check h2/h3 text or .jobs-similar-jobs here because those selectors also
            # match the "Similar jobs" recommendation section at the bottom of real job detail pages.
            current_url = page.url
            if any(p in current_url for p in ("similarJobs=true", "/jobs/collections/", "/jobs/search/")):
                return None

            # Strategy 1: aria-label is the most reliable selector in LinkedIn's new design.
            # "Easy Apply to this job" is the aria-label on the top-card button.
            for aria_sel in (
                "a[aria-label='Easy Apply to this job']",
                "button[aria-label='Easy Apply to this job']",
                "[aria-label*='Easy Apply']",
            ):
                try:
                    btn = page.locator(aria_sel).first
                    if btn.count() > 0:
                        bb = btn.bounding_box()
                        if bb:
                            return btn
                except Exception:
                    pass

            # Strategy 2: old-style class-based selectors (still work on some pages).
            card = page.locator(".jobs-unified-top-card, .job-view-layout").first
            if card.count() > 0:
                try:
                    for sel in (
                        "button.jobs-apply-button:has-text('Easy Apply')",
                        "a.jobs-apply-button:has-text('Easy Apply')",
                    ):
                        btn = card.locator(sel).first
                        if btn.count() > 0 and btn.bounding_box():
                            return btn

                    for el in card.locator("button, [role='button'], a").all():
                        if el.bounding_box():
                            text = (el.inner_text(timeout=500) or "").strip().lower()
                            if text == "easy apply":
                                return el
                except Exception:
                    pass

            # Strategy 3: navigator fallback — check the a11y tree.
            btn = find_button(page, "easy apply")
            if btn is not None:
                try:
                    # Verify the button's aria-label is the job-specific one, not a card
                    # from the "Similar jobs" section (those links have no aria-label or a
                    # different one).
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    text = (btn.inner_text(timeout=500) or "").strip().lower()
                    if aria == "easy apply to this job" or text == "easy apply":
                        return btn
                except Exception:
                    pass

            # Wait briefly and scroll up to ensure the top card is visible for next check.
            _human_delay(0.7, 1.1)
            page.mouse.wheel(0, -500)  # scroll up to keep the top card in view

        return None

    def _classify_apply_button_failure(self, page: Page, company: str, title: str) -> str:
        self._save_debug_snapshot(page, company, title)

        # Check for a URL-based Similar Jobs / search redirect first.
        # We avoid h2/h3 text or .jobs-similar-jobs CSS checks because those also match the
        # "Similar jobs" recommendation section visible at the bottom of real job detail pages.
        current_url = page.url
        if any(p in current_url for p in ("similarJobs=true", "/jobs/collections/", "/jobs/search/")):
            return (
                "Job listing no longer available — LinkedIn redirected to a job search page. "
                "The posting has likely expired or been removed."
            )

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
                _human_delay(1.5, 2.5)  # wait for "Application sent!" success modal
                self._dismiss_modal(page)  # close modal before next page.goto()
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
                # Detect decimal-number constraint first (before the skip-if-filled check)
                # so we can clear non-numeric drafts in such fields.
                decimal_min: float | None = None
                try:
                    placeholder = (field.locator.get_attribute("placeholder") or "").strip()
                    if re.search(r"decimal|number\s+(larger|greater|more)\s+than|enter a number", placeholder, re.I):
                        m = re.search(r"(larger|greater|more)\s+than\s+([\d.]+)", placeholder, re.I)
                        decimal_min = float(m.group(2)) if m else 0.0
                        print(f"DEBUG: Field '{label}' detected as decimal-number (min={decimal_min}), placeholder={placeholder!r}")
                except Exception:
                    pass

                # Skip if already filled — UNLESS:
                #   (a) the field is marked aria-invalid, OR
                #   (b) this is a decimal field and the existing value is non-numeric
                try:
                    existing = field.locator.input_value()
                    if existing:
                        is_invalid = field.locator.get_attribute("aria-invalid") == "true"
                        decimal_value_invalid = (
                            decimal_min is not None
                            and not re.fullmatch(r"[\d.]+", existing.strip())
                        )
                        if not is_invalid and not decimal_value_invalid:
                            print(f"DEBUG: Field '{label}' already has value: {existing!r}")
                            continue
                        reason = "aria-invalid" if is_invalid else "non-numeric value in decimal field"
                        print(f"DEBUG: Field '{label}' clearing ({reason}): {existing[:60]!r}")
                        field.locator.fill("")
                        _human_delay(0.1, 0.3)
                except Exception:
                    pass

                if decimal_min is not None:
                    # Field expects a decimal > decimal_min
                    filled = answer_question(label, "number", company=company, job_title=title)
                    print(f"DEBUG: Decimal answer for '{label}': {filled}")
                    if filled.is_manual_review:
                        manual_review_questions.append(label)
                    else:
                        _m = re.search(r"\d+\.?\d*", filled.value or "")
                        try:
                            num_val = float(_m.group()) if _m else 0.0
                        except ValueError:
                            num_val = 0.0
                        if num_val <= decimal_min:
                            num_val = decimal_min + 1.0
                        answer_text = f"{num_val:.1f}".rstrip("0").rstrip(".")
                        field.locator.fill(answer_text)
                        filled_values[label] = answer_text
                        _human_delay(0.3, 0.6)
                else:
                    filled = answer_question(label, "text", company=company, job_title=title)
                    print(f"DEBUG: Answer for '{label}': {filled}")
                    if filled.is_manual_review:
                        manual_review_questions.append(label)
                    elif filled.value:
                        answer_text = filled.value
                        if re.search(r"\byrs?\b.*exp|\byears?\b.*exp|years? of exp", label, re.I):
                            digits_only = re.sub(r"[^\d]", "", answer_text)
                            if digits_only:
                                answer_text = digits_only
                        answer_text = _enforce_maxlength(field.locator, answer_text)
                        _type_into(field.locator, answer_text)
                        filled_values[label] = answer_text
                        _human_delay(0.3, 0.8)

            elif field.field_type == "number":
                try:
                    if field.locator.input_value():
                        is_invalid = field.locator.get_attribute("aria-invalid") == "true"
                        if not is_invalid:
                            print(f"DEBUG: Field '{label}' already has value: {field.locator.input_value()!r}")
                            continue
                        field.locator.fill("")
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
        """
        Find aria-invalid fields, clear them, and re-fill correctly.

        Handles two distinct cases:
        - Character-limit errors: truncate the current value to the limit reported
          in the adjacent error message (no LLM call needed).
        - Numeric-format errors: re-ask the LLM as a number type and fill digits only.
        """
        touched = False
        try:
            invalid_fields = scope.locator("[aria-invalid='true']").all()
            for field_loc in invalid_fields:
                try:
                    # Derive label
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

                    # Find the adjacent error message for this field
                    char_limit: int | None = None
                    field_id = field_loc.get_attribute("id") or ""
                    error_selectors = [
                        f"[id*='{field_id}'][class*='error']" if field_id else None,
                        ".artdeco-inline-feedback--error",
                    ]
                    for err_sel in error_selectors:
                        if not err_sel:
                            continue
                        try:
                            err_els = scope.locator(err_sel).all()
                            for err_el in err_els:
                                err_txt = (err_el.inner_text(timeout=400) or "").strip()
                                if err_txt:
                                    print(f"DEBUG: fix_validation error text: {err_txt!r}")
                                    limit = _parse_char_limit_from_error(err_txt)
                                    if limit:
                                        char_limit = limit
                                        break
                        except Exception:
                            pass
                        if char_limit:
                            break

                    # Case 1: character-limit error — truncate without re-asking
                    if char_limit is not None:
                        try:
                            current = field_loc.input_value() or ""
                        except Exception:
                            current = ""
                        if len(current) > char_limit:
                            truncated = current[:char_limit].rsplit(" ", 1)[0].rstrip(".,;: ")
                            if not truncated:
                                truncated = current[:char_limit]
                        else:
                            # Value is within limit — error might be stale; touch anyway
                            truncated = current
                        print(f"DEBUG: Char-limit fix: trimming to {char_limit} chars (was {len(current)})")
                        field_loc.click()
                        field_loc.fill(truncated)
                        _human_delay(0.2, 0.4)
                        touched = True
                        continue

                    # Case 2a: decimal-number-larger-than-X constraint
                    decimal_min_req: float | None = None
                    for err_sel2 in error_selectors:
                        if not err_sel2:
                            continue
                        try:
                            for err_el2 in scope.locator(err_sel2).all():
                                et = (err_el2.inner_text(timeout=400) or "").strip()
                                m2 = re.search(
                                    r"decimal number larger than\s+([\d.]+)|"
                                    r"number\s+(larger|greater|more)\s+than\s+([\d.]+)|"
                                    r"must be (greater|larger) than\s+([\d.]+)",
                                    et, re.I,
                                )
                                if m2:
                                    raw = next(g for g in m2.groups() if g and re.match(r"[\d.]+", g))
                                    decimal_min_req = float(raw)
                                    break
                        except Exception:
                            pass
                        if decimal_min_req is not None:
                            break

                    # Also check the placeholder for the decimal hint
                    if decimal_min_req is None:
                        try:
                            ph = (field_loc.get_attribute("placeholder") or "").lower()
                            m_ph = re.search(r"(larger|greater|more)\s+than\s+([\d.]+)", ph, re.I)
                            if m_ph:
                                decimal_min_req = float(m_ph.group(2))
                        except Exception:
                            pass

                    if decimal_min_req is not None:
                        # Collect all visible error texts for this field to pass as context
                        _all_errs = []
                        for _es in error_selectors:
                            if not _es:
                                continue
                            try:
                                for _ee in scope.locator(_es).all():
                                    _et = (_ee.inner_text(timeout=400) or "").strip()
                                    if _et:
                                        _all_errs.append(_et)
                            except Exception:
                                pass
                        _err_ctx = "; ".join(dict.fromkeys(_all_errs))
                        print(f"DEBUG: decimal-min fix for '{label}', min={decimal_min_req}, error={_err_ctx!r}")
                        filled = answer_question(label, "number", company=company, job_title=title, validation_error=_err_ctx)
                        _m2 = re.search(r"\d+\.?\d*", filled.value or "")
                        try:
                            num_val = float(_m2.group()) if _m2 else 0.0
                        except ValueError:
                            num_val = 0.0
                        if num_val <= decimal_min_req:
                            num_val = decimal_min_req + 1.0
                        answer_str = f"{num_val:.1f}".rstrip("0").rstrip(".")
                        field_loc.click()
                        field_loc.fill(answer_str)
                        _human_delay(0.2, 0.4)
                        touched = True
                        continue

                    # Case 2b: likely a numeric/format error — re-ask as number
                    # Collect error text for LLM context
                    _err_ctx_b = ""
                    try:
                        for _es in error_selectors:
                            if not _es:
                                continue
                            for _ee in scope.locator(_es).all():
                                _et = (_ee.inner_text(timeout=400) or "").strip()
                                if _et:
                                    _err_ctx_b = _et
                                    break
                            if _err_ctx_b:
                                break
                    except Exception:
                        pass
                    field_loc.click()
                    field_loc.fill("")
                    _human_delay(0.2, 0.4)

                    filled = answer_question(label, "number", company=company, job_title=title, validation_error=_err_ctx_b)
                    if filled.value:
                        _m3 = re.search(r"\d+\.?\d*", filled.value)
                        field_loc.fill(_m3.group() if _m3 else filled.value)
                        _human_delay(0.2, 0.4)
                        touched = True
                except Exception:
                    continue
        except Exception:
            pass

        # Fallback: handle decimal/char-limit errors on fields that are NOT marked
        # aria-invalid (LinkedIn often shows .artdeco-inline-feedback--error without
        # setting aria-invalid on the input).  Find the field via aria-describedby.
        try:
            for err_el in scope.locator(".artdeco-inline-feedback--error").all():
                try:
                    err_txt = (err_el.inner_text(timeout=400) or "").strip()
                    if not err_txt:
                        continue
                    print(f"DEBUG: fix_validation fallback error: {err_txt!r}")

                    # Try to find the associated input via aria-describedby first,
                    # then fall back to walking up the DOM tree.
                    err_id = (err_el.get_attribute("id") or "").strip()
                    inp_loc = None
                    if err_id:
                        candidate = scope.locator(f"[aria-describedby*='{err_id}']").first
                        if candidate.count() > 0:
                            inp_loc = candidate
                    if inp_loc is None:
                        # Walk up the DOM (up to 5 levels) to find a parent that
                        # also contains a text input.
                        for _lvl in range(1, 6):
                            ancestor_xpath = "xpath=" + "/".join([".."] * _lvl)
                            ancestor = err_el.locator(ancestor_xpath)
                            if ancestor.count() == 0:
                                break
                            inp_candidate = ancestor.locator(
                                "input[type='text'], input[type='number'], input:not([type])"
                            ).first
                            if inp_candidate.count() > 0:
                                inp_loc = inp_candidate
                                break
                    if inp_loc is None:
                        continue

                    # Decimal constraint
                    m_dec = re.search(
                        r"decimal number larger than\s*([\d.]+)|"
                        r"number\s+(?:larger|greater|more)\s+than\s*([\d.]+)",
                        err_txt, re.I,
                    )
                    if m_dec:
                        raw = next(g for g in m_dec.groups() if g and re.match(r"[\d.]+", g))
                        dmin = float(raw)
                        # Derive label for the input to pass to LLM
                        _fb_label = ""
                        try:
                            _fb_label = (inp_loc.get_attribute("aria-label") or "").strip()
                            if not _fb_label:
                                _fid = (inp_loc.get_attribute("id") or "").strip()
                                if _fid:
                                    _lbl = scope.locator(f"label[for='{_fid}']")
                                    if _lbl.count() > 0:
                                        _fb_label = (_lbl.inner_text(timeout=400) or "").strip()
                        except Exception:
                            pass
                        filled_fb = answer_question(_fb_label or "numeric field", "number", company=company, job_title=title, validation_error=err_txt)
                        _m4 = re.search(r"\d+\.?\d*", filled_fb.value or "")
                        try:
                            num_val = float(_m4.group()) if _m4 else 0.0
                        except ValueError:
                            num_val = 0.0
                        if num_val <= dmin:
                            num_val = dmin + 1.0
                        answer_str = f"{num_val:.1f}".rstrip("0").rstrip(".")
                        print(f"DEBUG: fix_validation fallback decimal: label={_fb_label!r} → {answer_str!r}")
                        inp_loc.click()
                        inp_loc.fill(answer_str)
                        _human_delay(0.2, 0.4)
                        touched = True
                        continue

                    # Character-limit constraint
                    char_limit_fb = _parse_char_limit_from_error(err_txt)
                    if char_limit_fb:
                        try:
                            current = inp_loc.input_value() or ""
                        except Exception:
                            current = ""
                        if len(current) > char_limit_fb:
                            truncated = current[:char_limit_fb].rsplit(" ", 1)[0].rstrip(".,;: ") or current[:char_limit_fb]
                            print(f"DEBUG: fix_validation fallback char-limit: trimming to {char_limit_fb} (was {len(current)})")
                            inp_loc.click()
                            inp_loc.fill(truncated)
                            _human_delay(0.2, 0.4)
                            touched = True
                except Exception:
                    continue
        except Exception:
            pass

        return touched

    def _dismiss_modal(self, page: Page) -> None:
        try:
            # "Done" closes the "Application sent!" success modal after submit.
            done_btn = page.locator("button:has-text('Done')").first
            if done_btn.count() > 0 and done_btn.is_visible():
                done_btn.click()
                _human_delay(0.5, 1)
                return

            # If a Save/Discard confirmation dialog is already open, handle it directly.
            discard = page.locator("button:has-text('Discard')").first
            if discard.count() > 0 and discard.is_visible():
                discard.click()
                _human_delay(0.5, 1)
                return

            # Click the X / Dismiss button on the main modal.
            dismiss = page.locator(
                "button[aria-label='Dismiss'], "
                "button[aria-label='Dismiss application'], "
                "button[aria-label='Close']"
            ).first
            if dismiss.count() > 0 and dismiss.is_visible():
                dismiss.click()
                # Wait up to 6 seconds for LinkedIn's "Save this application?" confirmation
                # dialog to appear, then click Discard.
                deadline = time.time() + 6.0
                while time.time() < deadline:
                    _human_delay(0.4, 0.6)
                    discard = page.locator("button:has-text('Discard')").first
                    if discard.count() > 0 and discard.is_visible():
                        discard.click()
                        _human_delay(0.3, 0.6)
                        return
                    # Also check if the modal is already gone (no confirmation needed)
                    if page.locator("[role='dialog']").count() == 0:
                        return
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
