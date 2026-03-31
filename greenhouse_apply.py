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
from pathlib import Path

from playwright.sync_api import (
    sync_playwright, Page, BrowserContext,
    TimeoutError as PWTimeoutError,
)
from thefuzz import fuzz

from config import RESUME_PATH
from form_filler import answer_question, clear_qa_log, get_qa_log, start_qa_log
from navigator import find_button, find_form_fields, find_file_upload
from core.models import ApplyResult

SESSION_FILE = Path("output/greenhouse_session.json")
RESUME_PATH_OBJ = Path(RESUME_PATH)
DEBUG_DIR = Path("output/debug")


def _human_delay(lo: float = 0.8, hi: float = 2.5) -> None:
    time.sleep(random.uniform(lo, hi))


def _type_into(locator, text: str, timeout: int = 5000) -> None:
    """Type text into a field. Raises PWTimeoutError if field is unresponsive."""
    try:
        locator.click(force=True, timeout=timeout)
    except Exception:
        pass
    try:
        locator.fill("")
    except Exception:
        pass
    locator.type(text, delay=random.randint(35, 90), timeout=timeout)


# ── Autocomplete helpers ─────────────────────────────────────────────────────

_AUTOCOMPLETE_LABEL_KEYWORDS = {
    "school", "university", "college", "degree", "discipline",
    "field of study", "major",
}

_DEGREE_SEARCH_TERMS = [
    ("bachelor", ["Bachelor"]),
    ("b.e",      ["Bachelor"]),
    ("b.tech",   ["Bachelor"]),
    ("b.s",      ["Bachelor"]),
    ("master",   ["Master"]),
    ("m.s",      ["Master"]),
    ("m.tech",   ["Master"]),
    ("phd",      ["Doctor", "Ph.D"]),
    ("doctor",   ["Doctor"]),
    ("associate",["Associate"]),
    ("mba",      ["MBA", "Master"]),
]

_SCHOOL_SEARCH_TERMS = [
    ("birla institute of technology and science", ["BITS", "Birla"]),
    ("bits pilani",                               ["BITS", "Birla"]),
    ("bits",                                      ["BITS", "Birla"]),
]

_DROPDOWN_SELECTORS = [
    "[role='listbox']",
    "[role='menu']",
    ".autocomplete-results",
    ".suggestion-list",
    "ul[id*='listbox']",
    "div[class*='dropdown']:visible",
    ".select2-container--open .select2-results__option",
    "[role='option']",
]

# ── Section headers that look like fields but aren't ────────────────────────

_SECTION_HEADER_LABELS: frozenset[str] = frozenset({
    "(optional) personal preferences",
    "voluntary self-identification",
    "voluntary self-identification of disability",
    "voluntary self-identification of veteran status",
})

# ── Policy checkbox keywords (auto-check these) ──────────────────────────────

_POLICY_CB_KEYWORDS = [
    "policy", "acknowledge", "agree", "consent", "terms",
    "privacy", "gdpr", "certify", "confirm", "understand",
    "authorization", "authorize", "application",
]


def _get_dropdown_options(page: Page, exclude: set[str] | None = None) -> list[tuple[str, object]]:
    """Return (text, locator) pairs for all visible dropdown options.

    Pass *exclude* (a set of text strings) to filter out options that were
    already visible before the current keystroke — this avoids matching
    options from unrelated dropdowns already rendered on the page.
    """
    COMBINED = (
        "[role='listbox'] [role='option'], "
        "[role='menu'] [role='menuitem'], "
        ".autocomplete-results li:visible, "
        ".suggestion-list li:visible, "
        "ul[id*='listbox'] li:visible, "
        ".select2-container--open .select2-results__option, "
        "[role='option']:visible"
    )
    results = []
    seen: set[str] = set()
    for loc in page.locator(COMBINED).all():
        try:
            if not loc.is_visible():
                continue
            txt = (loc.text_content() or "").strip()
            if not txt or txt in seen:
                continue
            if any(x in txt.lower() for x in ("please select", "searching", "loading", "no results")):
                continue
            seen.add(txt)
            if exclude and txt in exclude:
                continue
            results.append((txt, loc))
        except Exception:
            continue
    return results


def _best_match(query: str, options: list[tuple[str, object]], threshold: int = 60) -> tuple[str, object] | None:
    """Return the best (text, locator) fuzzy match above threshold, or None."""
    best_score = 0
    best = None
    q = query.lower()
    for txt, loc in options:
        score = max(
            fuzz.ratio(q, txt.lower()),
            fuzz.partial_ratio(q, txt.lower()),
            fuzz.token_set_ratio(q, txt.lower()),
        )
        if score > best_score:
            best_score = score
            best = (txt, loc)
    if best_score >= threshold:
        return best
    return None


def _fill_autocomplete(page: Page, locator, desired_value: str) -> bool:
    """
    Fill a Greenhouse autocomplete field by typing a partial query and
    clicking the best fuzzy-matched option from the dropdown.

    Snapshots pre-existing visible options before typing so that options
    from unrelated dropdowns already on the page are excluded.

    Returns True if an option was clicked, False if fallback (typed text left).
    """
    search_terms = _resolve_search_terms(desired_value)

    for attempt, query in enumerate(search_terms):
        prefix = query[:5]
        try:
            locator.click(force=True, timeout=2000)
        except Exception:
            pass
        try:
            locator.fill("")
        except Exception:
            pass

        # Snapshot already-visible options so we can exclude them later
        pre_existing: set[str] = {txt for txt, _ in _get_dropdown_options(page)}

        for ch in prefix:
            locator.type(ch, delay=random.randint(50, 100))

        # Wait up to 3s for a NEW dropdown to appear
        dropdown_appeared = False
        for sel in _DROPDOWN_SELECTORS:
            try:
                page.wait_for_selector(sel, timeout=3000, state="visible")
                dropdown_appeared = True
                break
            except Exception:
                continue

        if dropdown_appeared:
            opts = _get_dropdown_options(page, exclude=pre_existing)
            match = _best_match(query, opts)
            if match:
                txt, loc = match
                print(f"      [AUTOCOMPLETE] '{query}' -> matched '{txt}' (clicking)")
                try:
                    loc.click(force=True, timeout=2000)
                    return True
                except Exception:
                    pass

        # Retry: type the full query
        if attempt == 0:
            try:
                locator.fill("")
            except Exception:
                pass
            remaining = query[len(prefix):]
            for ch in remaining:
                locator.type(ch, delay=random.randint(50, 100))
            time.sleep(1.5)
            opts = _get_dropdown_options(page, exclude=pre_existing)
            if opts:
                match = _best_match(query, opts)
                if match:
                    txt, loc = match
                    print(f"      [AUTOCOMPLETE] retry '{query}' -> matched '{txt}' (clicking)")
                    try:
                        loc.click(force=True, timeout=2000)
                        return True
                    except Exception:
                        pass

    # Fallback: leave what's typed
    print(f"      [AUTOCOMPLETE] No match for '{desired_value}' — leaving typed text")
    try:
        locator.fill(desired_value[:50])
    except Exception:
        pass
    return False


def _resolve_search_terms(desired_value: str) -> list[str]:
    """Return an ordered list of search queries (short common forms first)."""
    low = desired_value.lower()
    for keyword, terms in _DEGREE_SEARCH_TERMS:
        if keyword in low:
            return terms + [desired_value]
    for keyword, terms in _SCHOOL_SEARCH_TERMS:
        if keyword in low:
            return terms + [desired_value]
    return [desired_value]


def _is_autocomplete_label(label: str) -> bool:
    low = label.lower()
    return any(kw in low for kw in _AUTOCOMPLETE_LABEL_KEYWORDS)


def _is_section_header(label: str) -> bool:
    return label.lower().strip().rstrip("*").strip() in _SECTION_HEADER_LABELS


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
        start_qa_log()
        result = ApplyResult(status="error", job_url=job_url, company=company, title=title)

        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=45_000)
            _human_delay(1.5, 3)

            apply_btn = (
                find_button(page, "apply for this job")
                or find_button(page, "apply now")
                or find_button(page, "apply")
            )
            if apply_btn is not None:
                apply_btn.click()
                _human_delay(1.5, 2.5)

            try:
                page.wait_for_selector(
                    "#application-form, form#application, form[id*='application']",
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
            self._save_debug_snapshot(page, company, title, prefix="greenhouse_timeout")
        except Exception as exc:
            result.status = "error"
            result.error_message = str(exc)
            self._save_debug_snapshot(page, company, title, prefix="greenhouse_exception")
        finally:
            result.qa_log = get_qa_log()
            clear_qa_log()

        return result

    def _fill_application(self, page: Page, result: ApplyResult) -> ApplyResult:
        # ── Resume upload ────────────────────────────────────────────────────
        if not RESUME_PATH_OBJ.exists():
            print(f"[DEBUG] Resume file not found at: {RESUME_PATH_OBJ}")
        else:
            try:
                upload_input = page.locator("input[type='file']").first
                if upload_input.count() > 0:
                    current_val = ""
                    try:
                        current_val = upload_input.input_value()
                    except Exception:
                        pass
                    if not current_val:
                        upload_input.set_input_files(str(RESUME_PATH_OBJ))
                        print(f"[DEBUG] Uploaded resume: {RESUME_PATH_OBJ}")
                        _human_delay(1, 2)
                    else:
                        print("[DEBUG] Resume already attached, skipping upload")
                else:
                    print("[DEBUG] No input[type='file'] found on page")
            except Exception as exc:
                print(f"[DEBUG] Resume upload error: {exc}")

        # ── Form fields ──────────────────────────────────────────────────────
        manual_questions = self._fill_fields(page, result.company, result.title)
        result.manual_questions.extend(manual_questions)
        if manual_questions:
            result.status = "manual_review"
            return result

        # ── Checkboxes (policy, consent, GDPR) ──────────────────────────────
        self._handle_checkboxes(page, result.company, result.title)

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

        try:
            page.wait_for_url(re.compile(r"confirmation|thank|success", re.IGNORECASE), timeout=15000)
        except Exception:
            _human_delay(3, 5)

        if self._is_submitted(page):
            result.status = "applied"
        else:
            result.status = "manual_review"
            result.manual_questions.append(
                "Form submission may have failed or requires review. Check the browser."
            )
            self._save_debug_snapshot(page, result.company, result.title, prefix="greenhouse_submit_check")

        return result

    def _fill_fields(self, page: Page, company: str, title: str) -> list[str]:
        manual: list[str] = []
        seen_labels: set[str] = set()

        # Two passes: some fields (e.g. "Please identify your race") are
        # revealed only after a preceding combobox is answered (e.g. Hispanic/Latino → No).
        for _pass in range(2):
            for field in find_form_fields(page):
                label = field.label
                if not label or label in seen_labels:
                    continue
                seen_labels.add(label)

                # ── Skip known section headers ────────────────────────────────
                if _is_section_header(label):
                    print(f"\n[DEBUG] Skipping section header: '{label}'")
                    continue

                # ── Skip search/filter boxes (e.g. phone country-code search) ─
                if field.field_type == "search" or label.strip().lower() == "search":
                    print(f"\n[DEBUG] Skipping search/filter field: '{label}'")
                    continue

                print(f"\n[DEBUG] Field: '{label}' | Type: '{field.field_type}' | Options: {field.options[:4] if field.options else []}")

                if field.field_type in ("text", "email", "tel", "textarea", "search", "url"):
                    # Skip if already filled
                    try:
                        if field.locator.input_value():
                            print(f"   -> Already filled, skipping")
                            continue
                    except Exception:
                        pass

                    # Skip non-visible/non-enabled fields (Bug 6)
                    try:
                        if not field.locator.is_visible():
                            print(f"   -> Not visible, skipping")
                            continue
                    except Exception:
                        continue

                    # Education autocomplete fields (school, degree, discipline)
                    if _is_autocomplete_label(label):
                        filled = answer_question(label, "text", company=company, job_title=title)
                        print(f"   -> AI Value for autocomplete '{label}': '{filled.value}'")
                        if filled.is_manual_review:
                            manual.append(label)
                        elif filled.value:
                            clicked = _fill_autocomplete(page, field.locator, filled.value)
                            if not clicked:
                                print(f"   [WARN] Autocomplete fallback for '{label}' — no option selected")
                            _human_delay(0.5, 1.0)
                        continue

                    # Combobox detection (select2 / aria combobox).
                    # Textareas are never comboboxes — they're always free-text.
                    is_combobox = False
                    if field.field_type != "textarea":
                        try:
                            cls = field.locator.get_attribute("class") or ""
                            role = field.locator.get_attribute("role") or ""
                            aria_auto = field.locator.get_attribute("aria-autocomplete") or ""
                            if ("select2" in cls or "select__input" in cls or
                                    role == "combobox" or aria_auto == "list"):
                                is_combobox = True
                        except Exception:
                            pass

                    if is_combobox:
                        self._fill_combobox(page, field, label, company, title, manual)
                        continue

                    # Standard text field
                    filled = answer_question(label, "text", company=company, job_title=title)
                    print(f"   -> AI Answered Text: '{filled.value}' (Manual: {filled.is_manual_review})")
                    if filled.is_manual_review:
                        manual.append(label)
                    elif filled.value:
                        value_to_type = filled.value
                        # Phone fields: strip country-code prefix (+91-... / +1 ...)
                        # because Greenhouse's country-code picker already adds it.
                        if field.field_type == "tel":
                            value_to_type = re.sub(r"^\+\d{1,3}[-\s]?", "", value_to_type)
                            print(f"   -> Phone (country-code stripped): '{value_to_type}'")
                        try:
                            if field.field_type == "textarea":
                                # Use fill() for long text — avoids per-character timeout
                                field.locator.click(force=True, timeout=3000)
                                field.locator.fill(value_to_type)
                            else:
                                _type_into(field.locator, value_to_type, timeout=5000)
                            _human_delay(0.3, 0.7)
                        except PWTimeoutError:
                            print(f"   [WARN] Timeout typing into '{label}', skipping")
                        except Exception as exc:
                            print(f"   [WARN] Error typing into '{label}': {exc}")

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
                        try:
                            field.locator.fill(digits)
                            _human_delay(0.3, 0.6)
                        except Exception as exc:
                            print(f"   [WARN] Error filling number '{label}': {exc}")

                elif field.field_type == "select":
                    if not field.options:
                        print(f"   -> No options found for select, skipping")
                        continue
                    filled = answer_question(
                        label, "dropdown", options=field.options, company=company, job_title=title
                    )
                    print(f"   -> AI Answered Select: '{filled.value}' (Manual: {filled.is_manual_review})")
                    if filled.is_manual_review:
                        manual.append(label)
                    elif filled.value:
                        try:
                            field.locator.select_option(label=filled.value)
                        except Exception:
                            try:
                                field.locator.select_option(value=filled.value)
                            except Exception:
                                pass
                        _human_delay(0.3, 0.7)

                elif field.field_type == "radio":
                    filled = answer_question(
                        label, "radio", options=field.options, company=company, job_title=title
                    )
                    print(f"   -> AI Answered Radio: '{filled.value}' (Manual: {filled.is_manual_review})")
                    if filled.is_manual_review:
                        manual.append(label)
                    elif filled.value:
                        group = page.locator(
                            "[role='radiogroup']:visible, fieldset:visible"
                        ).filter(has_text=label)
                        if group.count() > 0:
                            radio_btn = group.first.locator("label").filter(has_text=filled.value).first
                            if radio_btn.count() > 0 and radio_btn.is_visible():
                                try:
                                    radio_btn.click(force=True, timeout=3000)
                                    _human_delay(0.3, 0.7)
                                except Exception:
                                    pass

        return manual

    def _fill_combobox(
        self,
        page: Page,
        field,
        label: str,
        company: str,
        title: str,
        manual: list[str],
    ) -> None:
        """
        Fill a select2/combobox input.

        Bug 1 fix: option lookup is scoped to the listbox this specific input
        controls (via aria-controls), NOT grabbed globally from the page.
        If the input has no aria-controls or the listbox is empty, falls back
        to async autocomplete (_fill_autocomplete).
        """
        try:
            # Click to trigger dropdown render FIRST — react-select sets
            # aria-controls dynamically only after the dropdown opens.
            field.locator.click(force=True, timeout=2000)
            _human_delay(0.5, 1.0)

            # Read aria-controls AFTER clicking so react-select has set it
            aria_controls = ""
            try:
                aria_controls = field.locator.get_attribute("aria-controls") or ""
            except Exception:
                pass

            combo_opts: list[str] = []
            opt_sel: str | None = None

            if aria_controls:
                # Scope option search ONLY to the associated listbox
                opt_sel = f"#{aria_controls} [role='option']"
                try:
                    page.wait_for_selector(f"#{aria_controls}", state="visible", timeout=2000)
                    for opt in page.locator(opt_sel).all():
                        try:
                            if not opt.is_visible():
                                continue
                            txt = (opt.text_content() or "").strip()
                            if txt and not any(x in txt.lower() for x in
                                               ("please select", "searching", "loading")):
                                combo_opts.append(txt)
                        except Exception:
                            continue
                except Exception:
                    pass

            if not combo_opts:
                # No scoped options found → treat as async autocomplete
                try:
                    field.locator.press("Escape")
                except Exception:
                    pass
                filled = answer_question(label, "text", company=company, job_title=title)
                print(f"   -> Combobox async search for '{label}': '{filled.value}'")
                if filled.is_manual_review:
                    manual.append(label)
                elif filled.value:
                    _fill_autocomplete(page, field.locator, filled.value)
                return

            print(f"      [COMBOBOX] '{label}' options: {combo_opts[:5]}")
            pick = answer_question(label, "dropdown", options=combo_opts, company=company, job_title=title)
            print(f"   -> AI picked combobox: '{pick.value}'")

            if pick.value and opt_sel:
                opt_loc = page.locator(opt_sel).filter(has_text=pick.value).first
                if opt_loc.count() > 0 and opt_loc.is_visible():
                    opt_loc.click(force=True, timeout=2000)
                else:
                    try:
                        field.locator.press("Escape")
                    except Exception:
                        pass
                    _type_into(field.locator, pick.value)
                    _human_delay(0.5, 1.0)
                    field.locator.press("Enter")
            else:
                try:
                    field.locator.press("Escape")
                except Exception:
                    pass

            _human_delay(0.5, 1.0)

        except Exception as exc:
            print(f"   [ERROR] Combobox crash for '{label}': {exc}")
        finally:
            try:
                field.locator.press("Escape")
            except Exception:
                pass

    def _handle_checkboxes(self, page: Page, company: str, title: str) -> None:
        """
        Handle all visible unchecked checkboxes.

        Policy/consent/application checkboxes are auto-checked.
        Others are passed to the AI with yes/no options.
        """
        for cb in page.locator("input[type='checkbox']:visible").all():
            try:
                if cb.is_checked():
                    continue

                # Resolve label text from multiple sources
                label_text = ""
                cb_id = cb.get_attribute("id") or ""
                if cb_id:
                    lbl = page.locator(f"label[for='{cb_id}']").first
                    if lbl.count() > 0:
                        label_text = (lbl.text_content() or "").strip()
                if not label_text:
                    ancestor = cb.locator("xpath=ancestor::label").first
                    if ancestor.count() > 0:
                        label_text = (ancestor.text_content() or "").strip()
                if not label_text:
                    try:
                        label_text = cb.evaluate(
                            "el => el.closest('div,li,p,span')?.textContent || ''"
                        ).strip()
                    except Exception:
                        pass

                print(f"\n[DEBUG] Checkbox: '{label_text[:100]}'")

                low = label_text.lower()
                if any(kw in low for kw in _POLICY_CB_KEYWORDS):
                    cb.check()
                    print(f"   -> Auto-checked (policy/consent keyword match)")
                    _human_delay(0.2, 0.5)
                elif label_text:
                    filled = answer_question(
                        label_text, "radio", options=["Yes", "No"],
                        company=company, job_title=title,
                    )
                    if filled.value and filled.value.strip().lower() == "yes":
                        cb.check()
                        print(f"   -> AI checked: Yes")
                        _human_delay(0.2, 0.5)
                    else:
                        print(f"   -> AI chose not to check: '{filled.value}'")
            except Exception as exc:
                print(f"   [WARN] Checkbox handling error: {exc}")
                continue

    def _is_submitted(self, page: Page) -> bool:
        url = page.url.lower()
        if "confirmation" in url or "thank" in url or "success" in url:
            return True
        for phrase in [
            "application received",
            "thank you for applying",
            "successfully submitted",
            "we'll be in touch",
        ]:
            try:
                if page.locator(f"text={phrase}").count() > 0:
                    return True
            except Exception:
                continue
        return False

    def _save_debug_snapshot(
        self, page: Page, company: str, title: str, prefix: str = "greenhouse_debug"
    ) -> None:
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
