/**
 * field-scanner.ts
 *
 * Port of legacy/navigator.py → find_form_fields + _label_for_element.
 * Pure DOM APIs only — no npm dependencies.
 * All helpers are exported so they can be unit-tested in isolation.
 */

import type { ApiField } from "../types/index.js";

// ── Label deduplication (port of _dedup_label) ────────────────────────────────
// LinkedIn injects the label text twice into the same node, e.g.:
//   "What is your notice period?What is your notice period?"
// If the string is exactly X+X (or X + separator + X), return X.

export function dedupLabel(text: string): string {
  const t = text.trim();
  const n = t.length;
  if (n < 4) return t;

  // Exact even split
  if (n % 2 === 0) {
    const half = n / 2;
    if (t.slice(0, half) === t.slice(half)) return t.slice(0, half).trim();
  }

  // Split on a single separator character between two identical halves
  for (const sep of ["\n", "\r\n", " "]) {
    const idx = t.indexOf(sep);
    if (idx !== -1) {
      const a = t.slice(0, idx).trim();
      const b = t.slice(idx + sep.length).trim();
      if (a && a === b) return a;
    }
  }

  return t;
}

// ── Label resolution (port of _label_for_element) ────────────────────────────
//
// Priority order (task spec):
//  1. aria-label attribute
//  2. aria-labelledby → referenced element(s) text
//  3. <label for="id"> association
//  4. parent <label> element text (input text stripped out)
//  5. preceding sibling text (first non-empty element/text node walking backwards)
//  6. placeholder attribute
//  7. name attribute

export function labelForElement(
  el: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
): string {
  const doc = el.ownerDocument;

  // 1. aria-label
  const ariaLabel = el.getAttribute("aria-label")?.trim();
  if (ariaLabel) return dedupLabel(ariaLabel);

  // 2. aria-labelledby (may reference multiple space-separated ids)
  const labelledBy = el.getAttribute("aria-labelledby")?.trim();
  if (labelledBy) {
    const text = labelledBy
      .split(/\s+/)
      .map((id) => doc.getElementById(id)?.textContent?.trim() ?? "")
      .filter(Boolean)
      .join(" ")
      .trim();
    if (text) return dedupLabel(text);
  }

  // 3. <label for="id">
  if (el.id) {
    const labelEl = doc.querySelector<HTMLLabelElement>(
      `label[for="${CSS.escape(el.id)}"]`
    );
    const text = labelEl?.textContent?.trim();
    if (text) return dedupLabel(text);
  }

  // 4. parent <label> (clone and remove the input node so we get only text)
  const parentLabel = el.closest<HTMLLabelElement>("label");
  if (parentLabel) {
    const clone = parentLabel.cloneNode(true) as HTMLLabelElement;
    clone
      .querySelectorAll("input, select, textarea")
      .forEach((child) => child.remove());
    const text = clone.textContent?.trim();
    if (text) return dedupLabel(text);
  }

  // 5. preceding sibling — walk backwards, skip empty nodes, take first text
  let sibling = el.previousSibling;
  while (sibling) {
    if (sibling.nodeType === Node.TEXT_NODE) {
      const text = sibling.textContent?.trim();
      if (text) return dedupLabel(text);
    } else if (sibling.nodeType === Node.ELEMENT_NODE) {
      const text = (sibling as Element).textContent?.trim();
      // Only use it if the element carries visible text (skip <br>, <hr>, etc.)
      if (text) return dedupLabel(text);
      // Empty element node — keep walking
    }
    sibling = sibling.previousSibling;
  }

  // 6. placeholder
  const placeholder = el.getAttribute("placeholder")?.trim();
  if (placeholder) return dedupLabel(placeholder);

  // 7. name attribute
  const name = el.getAttribute("name")?.trim();
  if (name) return dedupLabel(name);

  return "";
}

// For radio/checkbox groups the group label comes from the ancestor
// <fieldset><legend> when present; otherwise falls back to labelForElement
// on the first radio/checkbox in the group.
export function labelForGroup(
  groupElements: HTMLInputElement[]
): string {
  const first = groupElements[0];
  if (!first) return "";

  // Ancestor <fieldset> → <legend>
  const fieldset = first.closest<HTMLFieldSetElement>("fieldset");
  if (fieldset) {
    const legend = fieldset.querySelector("legend");
    const text = legend?.textContent?.trim();
    if (text) return dedupLabel(text);
  }

  // Fallback: resolve label for the first element in the group
  return labelForElement(first);
}

// ── Main scanner ──────────────────────────────────────────────────────────────

const SKIP_TYPES = new Set([
  "hidden",
  "submit",
  "button",
  "reset",
  "image",
  "file",
]);

export function scanFields(root: Document | Element): ApiField[] {
  const searchRoot: Element =
    root instanceof Document ? root.documentElement : root;

  const results: ApiField[] = [];
  const seenLabels = new Set<string>();

  function addField(field: ApiField): void {
    if (!field.label) return;
    if (seenLabels.has(field.label)) return; // dedup by label, keep first
    seenLabels.add(field.label);
    results.push(field);
  }

  // ── Pass 1: collect radio/checkbox groups by name ─────────────────────────
  // Process these first so they are excluded from the plain-input pass.
  const radioMap = new Map<
    string,
    { type: "radio" | "checkbox"; elements: HTMLInputElement[] }
  >();

  const allInputs =
    searchRoot.querySelectorAll<HTMLInputElement>("input");
  for (const input of allInputs) {
    const type = (input.getAttribute("type") || "text").toLowerCase();
    if (type !== "radio" && type !== "checkbox") continue;
    const name = input.getAttribute("name") ?? "";
    const key = `${type}::${name}`;
    if (!radioMap.has(key)) {
      radioMap.set(key, { type: type as "radio" | "checkbox", elements: [] });
    }
    radioMap.get(key)!.elements.push(input);
  }

  for (const { type, elements } of radioMap.values()) {
    const label = labelForGroup(elements);
    if (!label) continue;
    const options = elements
      .map((el) => el.getAttribute("value") ?? el.value ?? "")
      .filter(Boolean);
    addField({
      name: elements[0].getAttribute("name") ?? "",
      label,
      type,
      options,
    });
  }

  // ── Pass 2: plain inputs (not hidden/submit/button/radio/checkbox) ─────────
  for (const input of allInputs) {
    const rawType = (input.getAttribute("type") || "text").toLowerCase();
    if (SKIP_TYPES.has(rawType) || rawType === "radio" || rawType === "checkbox") {
      continue;
    }
    const label = labelForElement(input);
    if (!label) continue;
    addField({ name: input.getAttribute("name") ?? "", label, type: rawType });
  }

  // ── Pass 3: <select> ──────────────────────────────────────────────────────
  for (const select of searchRoot.querySelectorAll<HTMLSelectElement>(
    "select"
  )) {
    const label = labelForElement(select);
    if (!label) continue;
    const options = Array.from(select.querySelectorAll("option"))
      .filter((opt) => opt.value !== "")
      .map((opt) => opt.textContent?.trim() ?? "")
      .filter(Boolean);
    addField({
      name: select.getAttribute("name") ?? "",
      label,
      type: "select",
      options,
    });
  }

  // ── Pass 4: <textarea> ────────────────────────────────────────────────────
  for (const textarea of searchRoot.querySelectorAll<HTMLTextAreaElement>(
    "textarea"
  )) {
    const label = labelForElement(textarea);
    if (!label) continue;
    addField({
      name: textarea.getAttribute("name") ?? "",
      label,
      type: "textarea",
    });
  }

  return results;
}
