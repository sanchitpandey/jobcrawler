"""
navigator.py
────────────
Accessibility-tree-based element discovery for job-application automation.

Replaces hardcoded CSS selectors with role/name fuzzy matching so the same
helpers work across LinkedIn, Indeed, and any other site.

Public API
----------
find_button(page, intent)     → Locator | None
find_form_fields(page)        → list[FormField]
find_modal(page)              → Locator | None
find_file_upload(page)        → Locator | None
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from playwright.sync_api import Locator, Page
from thefuzz import fuzz

# Minimum fuzzy-match score (0–100) to accept a candidate.
FUZZY_THRESHOLD = 60


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FormField:
    """A visible form field extracted from the accessibility tree."""

    label: str
    """Human-readable label / question text."""

    field_type: str
    """One of: 'text', 'number', 'email', 'tel', 'textarea',
    'select', 'radio', 'checkbox', 'file', 'unknown'."""

    locator: Locator
    """Playwright locator that resolves to the field element."""

    options: list[str] = field(default_factory=list)
    """For 'select' / 'radio' / 'checkbox' fields: the available choices."""


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Lower-case, collapse whitespace, strip punctuation."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _fuzzy_match(candidate: str, intent: str) -> int:
    """Return the best fuzzy-match score between *candidate* and *intent*."""
    c = _normalize(candidate)
    i = _normalize(intent)
    return max(
        fuzz.ratio(c, i),
        fuzz.partial_ratio(c, i),
        fuzz.token_set_ratio(c, i),
    )


def _a11y_snapshot(page: Page) -> dict[str, Any]:
    """Return the full accessibility snapshot, or an empty dict on failure."""
    try:
        snapshot = page.accessibility.snapshot(interesting_only=False)
        return snapshot or {}
    except Exception:
        return {}


def _walk_nodes(node: dict[str, Any]):
    """Depth-first generator over every node in an a11y snapshot tree."""
    yield node
    for child in node.get("children", []):
        yield from _walk_nodes(child)


def _button_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all nodes whose role is 'button' or 'link'."""
    return [
        n for n in _walk_nodes(snapshot)
        if n.get("role") in ("button", "link")
    ]


def _dialog_nodes(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Return all nodes whose role is 'dialog' or 'alertdialog'."""
    return [
        n for n in _walk_nodes(snapshot)
        if n.get("role") in ("dialog", "alertdialog")
    ]


def _candidate_name(node: dict[str, Any]) -> str:
    """Best human-readable name for an a11y node."""
    return node.get("name") or node.get("description") or node.get("value") or ""


# ─────────────────────────────────────────────────────────────────────────────
# Fallback: DOM text search
# ─────────────────────────────────────────────────────────────────────────────

def _dom_button_fallback(page: Page, intent: str) -> Locator | None:
    """
    Scan every <button> and <a role='button'> element in the DOM and return
    the first whose visible text or aria-label fuzzy-matches *intent*.
    """
    candidates = page.locator("button, a[role='button'], [role='button']").all()
    best_score = 0
    best_locator: Locator | None = None

    for btn in candidates:
        try:
            if not btn.bounding_box():
                continue
            text = (btn.inner_text(timeout=500) or "").strip()
            aria = (btn.get_attribute("aria-label") or "").strip()
            name = text or aria
            if not name:
                continue
            score = _fuzzy_match(name, intent)
            if score > best_score:
                best_score = score
                best_locator = btn
        except Exception:
            continue

    if best_score >= FUZZY_THRESHOLD:
        return best_locator
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def find_button(page: Page, intent: str) -> Locator | None:
    """
    Find the most relevant button on *page* that matches *intent*.

    Strategy (fallback chain):
    1. Accessibility-tree snapshot — walk role=button/link nodes, fuzzy-match
       by name/description.
    2. DOM text search — iterate all visible button elements and match by
       inner-text or aria-label.
    3. Return None if nothing passes the FUZZY_THRESHOLD.

    Parameters
    ----------
    page:
        Active Playwright page.
    intent:
        Natural-language description of the button, e.g.
        ``"Easy Apply"``, ``"Submit application"``, ``"Continue to next step"``.

    Returns
    -------
    Playwright ``Locator`` pointing to the matched button, or ``None``.
    """
    # ── 1. Accessibility tree ────────────────────────────────────────────────
    snapshot = _a11y_snapshot(page)
    if snapshot:
        best_score = 0
        best_name: str = ""

        for node in _button_nodes(snapshot):
            name = _candidate_name(node)
            if not name:
                continue
            score = _fuzzy_match(name, intent)
            if score > best_score:
                best_score = score
                best_name = name

        if best_score >= FUZZY_THRESHOLD and best_name:
            # Resolve: try intent text first (short, exact), then best_name.
            # Iterate ALL matches (not just .first) to skip invisible duplicates.
            for name_to_try in [intent, best_name]:
                pat = re.compile(re.escape(name_to_try), re.IGNORECASE)
                for role in ("button", "link"):
                    try:
                        for locator in page.get_by_role(role, name=pat).all():
                            if locator.bounding_box():
                                return locator
                    except Exception:
                        pass

    # ── 2. DOM text search fallback ──────────────────────────────────────────
    # Pre-check: direct :has-text() before expensive fuzzy scan
    # Cover button, a, and any role='button' element
    for sel in (
        f"button:has-text('{intent}')",
        f"a:has-text('{intent}')",
        f"[role='button']:has-text('{intent}')",
    ):
        try:
            for el in page.locator(sel).all():
                if el.bounding_box():
                    return el
        except Exception:
            pass

    return _dom_button_fallback(page, intent)


def find_form_fields(page: Page) -> list[FormField]:
    """
    Extract all visible form fields with their labels from the current page.

    Scopes search to the active modal (if any) to avoid picking up background
    page elements.  Uses ``bounding_box()`` instead of ``:visible`` so that
    LinkedIn's custom-styled controls (which often lack a native ``type``
    attribute) are detected correctly.

    Returns
    -------
    List of :class:`FormField` objects ordered by DOM appearance.
    """
    fields: list[FormField] = []

    # ── Scope to modal so background-page fields are excluded ────────────────
    scope = find_modal(page) or page

    # ── Text / number / email / tel / textarea ───────────────────────────────
    text_candidates = scope.locator(
        "input:not([type='hidden']):not([type='radio']):not([type='checkbox'])"
        ":not([type='file']), textarea"
    ).all()
    for el in text_candidates:
        try:
            tag = el.evaluate("e => e.tagName.toLowerCase()")
        except Exception:
            tag = "input"

        if tag == "textarea":
            input_type = "textarea"
        else:
            raw_type = (el.get_attribute("type") or "text").lower()
            input_type = raw_type if raw_type in (
                "text", "number", "email", "tel", "search", "url"
            ) else "text"

        # Skip react-select / styled-component dummy required inputs:
        # they are type='text' with no id and class names like
        # 'remix-css-...-requiredInput' or 'css-...-a11yText'.
        # These are invisible, have no label, and corrupt nth-index counts.
        el_id = ""
        el_class = ""
        try:
            el_id = el.get_attribute("id") or ""
            el_class = " ".join(el.get_attribute("class") or "")
        except Exception:
            pass
        if not el_id and ("requiredInput" in el_class or "a11yText" in el_class):
            continue

        # Build a STABLE locator: use #id when available so that nth-index
        # drift (caused by react-select injecting DOM nodes during interactions)
        # never causes us to fill the wrong element.
        if el_id:
            stable = page.locator(f"#{el_id}")
        else:
            # No id: use aria-label as a unique selector if present
            el_aria = ""
            try:
                el_aria = el.get_attribute("aria-label") or ""
            except Exception:
                pass
            if el_aria:
                stable = page.locator(f"[aria-label='{el_aria}']").first
            else:
                stable = el  # last resort: nth-based

        label = _label_for_element(page, stable)
        if not label:
            continue
        fields.append(FormField(label=label, field_type=input_type, locator=stable))

    # ── Select dropdowns ─────────────────────────────────────────────────────
    for el in scope.locator("select").all():
        try:
            pass # Removed bounding_box() check
        except Exception:
            continue
        label = _label_for_element(page, el)
        if not label:
            continue
        options = [
            (opt.text_content() or "").strip()
            for opt in el.locator("option").all()
            if opt.get_attribute("value") not in ("", None)
        ]
        fields.append(FormField(label=label, field_type="select", locator=el, options=options))

    # ── Radio groups / fieldsets ─────────────────────────────────────────────
    for group in scope.locator("[role='radiogroup'], fieldset").all():
        try:
            pass # Removed bounding_box() check
        except Exception:
            continue
        legend_el = group.locator("legend, [role='group'] > span").first
        try:
            legend = (legend_el.text_content() or "").strip() if legend_el.count() else ""
        except Exception:
            legend = ""
        if not legend:
            continue
        options = [
            (lbl.text_content() or "").strip()
            for lbl in group.locator("label").all()
        ]
        radio_input = group.locator("input[type='radio']").first
        fields.append(
            FormField(label=legend, field_type="radio", locator=radio_input, options=options)
        )

    return fields


def find_modal(page: Page) -> Locator | None:
    """
    Find the active dialog / modal on the page.

    Strategy (fallback chain):
    1. Accessibility-tree snapshot — look for role=dialog or role=alertdialog.
    2. DOM selector ``[role='dialog']``.
    3. Return None if nothing is found.

    Returns
    -------
    Playwright ``Locator`` for the outermost dialog element, or ``None``.
    """
    # ── 1. Accessibility tree ────────────────────────────────────────────────
    snapshot = _a11y_snapshot(page)
    if snapshot:
        dialog_nodes = _dialog_nodes(snapshot)
        if dialog_nodes:
            # Try to resolve by role selector
            try:
                locator = page.get_by_role("dialog").first
                if locator.count() > 0 and locator.is_visible():
                    return locator
            except Exception:
                pass

    # ── 2. DOM fallback — ordered from most-specific to most-generic ─────────
    for sel in [
        "[role='dialog']",
        ".jobs-easy-apply-modal",
        ".artdeco-modal",
        "[aria-modal='true']",
        "[data-test-modal]",
        "[data-test-modal-container]",
    ]:
        try:
            locator = page.locator(sel).first
            if locator.count() > 0 and locator.bounding_box():
                return locator
        except Exception:
            continue

    return None


def find_file_upload(page: Page) -> Locator | None:
    """
    Find a file-input element for resume/document upload.

    Strategy (fallback chain):
    1. Accessibility-tree snapshot — look for role=textbox or button nodes
       whose name hints at file / upload / resume.
    2. DOM selector ``input[type='file']``.
    3. Return None if nothing is found.

    Returns
    -------
    Playwright ``Locator`` for the ``<input type='file'>`` element, or ``None``.
    """
    upload_keywords = ["resume", "upload", "cv", "attach", "file", "document"]

    # ── 1. Accessibility tree — named upload button hint ─────────────────────
    snapshot = _a11y_snapshot(page)
    if snapshot:
        for node in _walk_nodes(snapshot):
            name = _normalize(_candidate_name(node))
            if any(kw in name for kw in upload_keywords):
                role = node.get("role", "")
                if role in ("button", "textbox", "generic"):
                    # Try to resolve via DOM after the a11y hint
                    break  # fall through to DOM search below

    # ── 2. DOM selector ──────────────────────────────────────────────────────
    try:
        locator = page.locator("input[type='file']").first
        if locator.count() > 0:
            return locator
    except Exception:
        pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Internal: label resolution (shared by find_form_fields)
# ─────────────────────────────────────────────────────────────────────────────

def _label_for_element(page: Page, el: Locator) -> str:
    """
    Return the best human-readable label for a form element.

    Priority:
    1. ``aria-label`` attribute
    2. ``<label for="…">`` association via element id
    3. ``placeholder`` attribute
    4. Ancestor ``<label>`` element text
    5. Empty string if nothing is found
    """
    try:
        aria_label = el.get_attribute("aria-label")
        if aria_label and aria_label.strip():
            return aria_label.strip()

        element_id = el.get_attribute("id")
        if element_id:
            label_el = page.locator(f"label[for='{element_id}']").first
            if label_el.count() > 0:
                text = (label_el.text_content() or "").strip()
                if text:
                    return text

        placeholder = el.get_attribute("placeholder")
        if placeholder and placeholder.strip():
            return placeholder.strip()

        ancestor_label = el.locator("xpath=ancestor::label").first
        if ancestor_label.count() > 0:
            text = (ancestor_label.text_content() or "").strip()
            if text:
                return text
    except Exception:
        pass
    return ""
