/**
 * form-filler.ts
 *
 * The "hands" of the extension — injects values into DOM elements with the
 * correct events so React/Angular controlled inputs register the change.
 *
 * Critical detail: React overrides HTMLInputElement.prototype.value via
 * Object.defineProperty, so a direct `el.value = x` assignment bypasses
 * its synthetic event system entirely. We grab the native setter from the
 * prototype and call it directly, then dispatch the real DOM events that
 * React's onChange ultimately wraps.
 */

import type { ApiField, AnswerItem } from "../types/index.js";
import { humanDelay, enforceMaxlength } from "./human-delay.js";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface FillResult {
  label: string;
  success: boolean;
  error?: string;
}

// ── cssEscape polyfill (jsdom doesn't ship it) ───────────────────────────────

const cssEscape: (s: string) => string =
  typeof CSS !== "undefined" && typeof CSS.escape === "function"
    ? CSS.escape.bind(CSS)
    : (s: string) => s.replace(/["\\]/g, "\\$&");

// ── React-safe native setters ─────────────────────────────────────────────────

const _nativeInputSetter = Object.getOwnPropertyDescriptor(
  HTMLInputElement.prototype,
  "value"
)?.set;

const _nativeTextareaSetter = Object.getOwnPropertyDescriptor(
  HTMLTextAreaElement.prototype,
  "value"
)?.set;

const _nativeSelectSetter = Object.getOwnPropertyDescriptor(
  HTMLSelectElement.prototype,
  "value"
)?.set;

/**
 * Internal: set the value of an input/textarea using the prototype's native
 * setter so React's value descriptor override doesn't swallow the change.
 * Exported for tests.
 */
export function setNativeValue(
  el: HTMLInputElement | HTMLTextAreaElement,
  value: string
): void {
  const setter =
    el instanceof HTMLTextAreaElement
      ? _nativeTextareaSetter
      : _nativeInputSetter;

  if (setter) {
    setter.call(el, value);
  } else {
    // Fallback for non-browser environments where the descriptor is missing.
    el.value = value;
  }

  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

// ── Per-type fillers ──────────────────────────────────────────────────────────

/** Fill a text input (React-compatible). Honours maxlength. */
export async function fillTextField(
  el: HTMLInputElement,
  value: string
): Promise<void> {
  const truncated = enforceMaxlength(el, value);
  el.focus();
  setNativeValue(el, truncated);
  el.blur();
}

/** Fill a textarea (React-compatible). Honours maxlength. */
export async function fillTextarea(
  el: HTMLTextAreaElement,
  value: string
): Promise<void> {
  const truncated = enforceMaxlength(el, value);
  el.focus();
  setNativeValue(el, truncated);
  el.blur();
}

/**
 * Match a candidate value against a list of option strings.
 * Priority (ported from legacy form_filler._match_option):
 *   1. Exact (case-insensitive)
 *   2. Substring (either direction)
 *   3. Boolean shorthands (yes/true/1 ↔ yes/true; no/false/0 ↔ no/false)
 *   4. Immediate / no-notice semantic → shortest matching option
 * Returns the original (un-lowercased) option string, or null.
 */
export function matchOption(value: string, options: string[]): string | null {
  const cand = value.toLowerCase().trim();

  for (const opt of options) {
    if (opt.toLowerCase() === cand) return opt;
  }
  for (const opt of options) {
    const o = opt.toLowerCase();
    if (cand.includes(o) || o.includes(cand)) return opt;
  }
  if (["yes", "true", "1"].includes(cand)) {
    for (const opt of options) {
      if (["yes", "true"].includes(opt.toLowerCase())) return opt;
    }
  }
  if (["no", "false", "0"].includes(cand)) {
    for (const opt of options) {
      if (["no", "false"].includes(opt.toLowerCase())) return opt;
    }
  }
  if (
    ["immediate", "0 day", "no notice", "available now"].some((kw) =>
      cand.includes(kw)
    )
  ) {
    for (const opt of options) {
      const o = opt.toLowerCase();
      if (
        ["immediate", "0", "less than 15", "< 15", "within 15"].some((kw) =>
          o.includes(kw)
        )
      ) {
        return opt;
      }
    }
    for (const opt of options) {
      const o = opt.toLowerCase();
      if (!["select an option", "select", "please select", ""].includes(o)) {
        return opt;
      }
    }
  }
  return null;
}

/**
 * Select an option in a <select> dropdown by visible text.
 * Uses matchOption() so notice-period and boolean semantics are preserved.
 */
export async function fillSelect(
  el: HTMLSelectElement,
  value: string
): Promise<void> {
  const options = Array.from(el.options);
  const optTexts = options.map((o) => (o.textContent ?? "").trim());
  const matched = matchOption(value, optTexts);
  if (!matched) return;
  const idx = optTexts.indexOf(matched);
  const match = options[idx];
  if (!match) return;

  // Use the native setter so React picks it up.
  if (_nativeSelectSetter) {
    _nativeSelectSetter.call(el, match.value);
  } else {
    el.selectedIndex = match.index;
  }
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

/**
 * Click the radio button in `container` whose value/label matches `value`.
 * Uses matchOption() over the input `value` attributes first; falls back
 * to label text matching if no value matches.
 */
export async function fillRadioGroup(
  container: Element,
  value: string,
  _options: string[]
): Promise<void> {
  const radios = Array.from(
    container.querySelectorAll<HTMLInputElement>('input[type="radio"]')
  );
  if (radios.length === 0) return;

  // 1. Match against input values via the shared matcher.
  const values = radios.map((r) => r.value);
  const matchedValue = matchOption(value, values);
  if (matchedValue) {
    radios.find((r) => r.value === matchedValue)?.click();
    return;
  }

  // 2. Fall back to matching by label text.
  const cand = value.trim().toLowerCase();
  const labels = Array.from(container.querySelectorAll("label"));
  for (const label of labels) {
    const text = (label.textContent ?? "").trim().toLowerCase();
    if (!text) continue;
    if (text === cand || text.includes(cand) || cand.includes(text)) {
      const forId = label.getAttribute("for");
      const radio =
        label.querySelector<HTMLInputElement>('input[type="radio"]') ||
        (forId
          ? (document.getElementById(forId) as HTMLInputElement | null)
          : null);
      if (radio) {
        radio.click();
        return;
      }
    }
  }
}

/** Set checkbox checked state. Uses click() so React/native handlers fire. */
export async function fillCheckbox(
  el: HTMLInputElement,
  checked: boolean
): Promise<void> {
  if (el.checked !== checked) el.click();
}

// ── Public API: fillField ────────────────────────────────────────────────────

/**
 * Locate the DOM element for `field` (within `root`, defaults to document)
 * and fill it with `answer.value`. Returns a FillResult so the caller can
 * audit per-field success/failure.
 */
export async function fillField(
  field: ApiField,
  answer: AnswerItem,
  root: ParentNode = document
): Promise<FillResult> {
  const label = field.label;
  if (answer.is_manual_review) {
    return { label, success: false, error: "manual_review" };
  }
  const value = answer.value;
  if (!value) {
    return { label, success: false, error: "empty_value" };
  }

  try {
    const el = locateElement(field, root);
    if (!el) {
      return { label, success: false, error: "element_not_found" };
    }

    switch (field.type) {
      case "select":
        if (!(el instanceof HTMLSelectElement)) {
          return { label, success: false, error: "type_mismatch" };
        }
        await fillSelect(el, value);
        return { label, success: true };

      case "textarea":
        if (!(el instanceof HTMLTextAreaElement)) {
          return { label, success: false, error: "type_mismatch" };
        }
        await fillTextarea(el, value);
        return { label, success: true };

      case "radio": {
        // For radios, locateElement returns the group container.
        await fillRadioGroup(el, value, field.options ?? []);
        return { label, success: true };
      }

      case "checkbox": {
        if (!(el instanceof HTMLInputElement)) {
          return { label, success: false, error: "type_mismatch" };
        }
        const truthy = ["yes", "true", "1", "on", "checked"].includes(
          value.toLowerCase().trim()
        );
        await fillCheckbox(el, truthy);
        return { label, success: true };
      }

      default: {
        // text / email / number / tel / url / date / etc.
        if (!(el instanceof HTMLInputElement)) {
          return { label, success: false, error: "type_mismatch" };
        }
        await fillTextField(el, value);
        return { label, success: true };
      }
    }
  } catch (err: unknown) {
    return {
      label,
      success: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

/**
 * Locate the DOM element for `field` within `root`, falling back through
 * id → name → aria-label. For radio fields, returns the group's container.
 */
function locateElement(field: ApiField, root: ParentNode): Element | null {
  const { id, name, label, type } = field;

  if (type === "radio") {
    // Find any radio in the group, then walk up to a fieldset/form-row.
    const radio =
      (name
        ? root.querySelector<HTMLInputElement>(
            `input[type="radio"][name="${cssEscape(name)}"]`
          )
        : null) ??
      (id
        ? (document.getElementById(id) as HTMLInputElement | null)
        : null);
    if (!radio) return null;
    return (
      radio.closest("fieldset") ||
      radio.closest('[role="radiogroup"]') ||
      radio.parentElement ||
      radio
    );
  }

  // Direct id lookup is the most reliable.
  if (id) {
    const byId = document.getElementById(id);
    if (byId) return byId;
  }

  const tag =
    type === "select"
      ? "select"
      : type === "textarea"
        ? "textarea"
        : "input";

  if (name) {
    const byName = root.querySelector(
      `${tag}[name="${cssEscape(name)}"]`
    );
    if (byName) return byName;
  }

  if (label) {
    const byAria = root.querySelector(
      `${tag}[aria-label="${cssEscape(label)}"]`
    );
    if (byAria) return byAria;
  }

  // Last-resort: walk <label>/<legend> text to find the associated element.
  // LinkedIn's React can reassign or strip element attributes between scan and
  // fill; matching by visible label text is more resilient.
  if (label && root instanceof Element) {
    const normLabel = label.toLowerCase().replace(/\s+/g, " ").trim();
    for (const lbl of root.querySelectorAll<HTMLElement>("label, legend")) {
      const text = (lbl.textContent ?? "").toLowerCase().replace(/\s+/g, " ").trim();
      if (!text.includes(normLabel) && !normLabel.includes(text)) continue;

      // Follow <label for="..."> association.
      const forId = lbl.getAttribute("for");
      if (forId) {
        const assoc = document.getElementById(forId);
        if (assoc && assoc.matches(tag)) return assoc;
      }

      // Search the nearest form-element container for a matching tag.
      const container =
        lbl.closest(".fb-dash-form-element") ??
        lbl.closest(".jobs-easy-apply-form-section__grouping") ??
        lbl.closest(".artdeco-text-input") ??
        lbl.parentElement;
      if (container) {
        const el = container.querySelector(
          `${tag}:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])`,
        );
        if (el) return el;
      }
    }
  }

  return null;
}

// ── Bulk fill helper ──────────────────────────────────────────────────────────

/**
 * Fill every field for which we have a non-manual-review answer, with a
 * human-like pause between each one. Returns a per-field result list so
 * the caller can log/report which fields succeeded.
 */
export async function fillAllFields(
  fields: ApiField[],
  answers: AnswerItem[],
  root: ParentNode = document
): Promise<FillResult[]> {
  const results: FillResult[] = [];
  const byLabel = new Map(answers.map((a) => [a.label, a]));

  for (let i = 0; i < fields.length; i++) {
    const field = fields[i];
    const answer = byLabel.get(field.label);

    if (!answer) {
      results.push({
        label: field.label,
        success: false,
        error: "no_answer",
      });
      continue;
    }

    const result = await fillField(field, answer, root);
    results.push(result);

    if (i < fields.length - 1) {
      await humanDelay(300, 800);
    }
  }

  return results;
}
