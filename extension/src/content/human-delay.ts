/**
 * human-delay.ts
 *
 * Human-like delay and typing simulation.
 * Ported from legacy/linkedin_apply.py _human_delay, _type_into, _enforce_maxlength.
 *
 * The goal is to make form filling indistinguishable from a careful human user:
 * randomised pauses between actions, character-by-character typing with realistic
 * keystroke events, and respecting maxlength attributes by truncating at word
 * boundaries instead of mid-word.
 */

/** Random integer in [lo, hi]. */
function randInt(lo: number, hi: number): number {
  return Math.floor(Math.random() * (hi - lo + 1)) + lo;
}

/**
 * Sleep for a random duration between `lo` and `hi` ms.
 * Defaults match legacy `_human_delay` (800-2500 ms).
 */
export function humanDelay(lo: number = 800, hi: number = 2500): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, randInt(lo, hi)));
}

/**
 * Short pause (200-600 ms) for micro-decisions between actions —
 * e.g. between focusing a field and typing into it.
 */
export function thinkDelay(): Promise<void> {
  return humanDelay(200, 600);
}

/**
 * Truncate `text` to fit within the element's `maxlength` attribute.
 * If truncation is needed, break at the last whitespace before the limit
 * to avoid chopping a word in half. Returns `text` unchanged if there
 * is no maxlength or it already fits.
 */
export function enforceMaxlength(el: HTMLElement, text: string): string {
  const raw = el.getAttribute("maxlength");
  if (!raw) return text;
  const max = parseInt(raw, 10);
  if (!Number.isFinite(max) || max <= 0 || text.length <= max) return text;

  const slice = text.slice(0, max);
  const lastSpace = slice.lastIndexOf(" ");
  // Only break at a word boundary if it's not absurdly early in the slice.
  if (lastSpace > Math.floor(max * 0.5)) {
    return slice.slice(0, lastSpace);
  }
  return slice;
}

/**
 * Type `text` into an input/textarea character by character, dispatching
 * keydown/input/keyup events for each char so React/Angular controlled
 * inputs see every keystroke. Honours the element's maxlength.
 *
 * NOTE: this does NOT use the React-native-setter trick — it relies on
 * per-char `input` events which React's onChange listener picks up. For
 * paste-style fast filling, prefer form-filler.fillTextField().
 */
export async function typeInto(
  el: HTMLInputElement | HTMLTextAreaElement,
  text: string,
  charDelayLo: number = 30,
  charDelayHi: number = 80
): Promise<void> {
  const truncated = enforceMaxlength(el, text);
  el.focus();
  el.dispatchEvent(new Event("focus", { bubbles: true }));

  // Clear current value first so we don't append to existing text.
  el.value = "";
  el.dispatchEvent(new Event("input", { bubbles: true }));

  for (const ch of truncated) {
    el.dispatchEvent(new KeyboardEvent("keydown", { key: ch, bubbles: true }));
    el.value = el.value + ch;
    el.dispatchEvent(new InputEvent("input", { bubbles: true, data: ch }));
    el.dispatchEvent(new KeyboardEvent("keyup", { key: ch, bubbles: true }));
    await new Promise((resolve) =>
      setTimeout(resolve, randInt(charDelayLo, charDelayHi))
    );
  }

  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new Event("blur", { bubbles: true }));
  el.blur();
}
