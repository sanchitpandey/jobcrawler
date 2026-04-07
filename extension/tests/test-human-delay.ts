/**
 * Tests for human-delay.ts.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  humanDelay,
  thinkDelay,
  enforceMaxlength,
  typeInto,
} from "../src/content/human-delay.js";
import { createMockInput, resetDom } from "./test-setup.js";

beforeEach(resetDom);

describe("humanDelay", () => {
  it("resolves within the requested range", async () => {
    const start = Date.now();
    await humanDelay(50, 100);
    const elapsed = Date.now() - start;
    expect(elapsed).toBeGreaterThanOrEqual(45); // small jitter tolerance
    expect(elapsed).toBeLessThan(250);
  });
});

describe("thinkDelay", () => {
  it("returns a promise that resolves", async () => {
    await expect(thinkDelay()).resolves.toBeUndefined();
  });
});

describe("enforceMaxlength", () => {
  it("returns text unchanged when no maxlength", () => {
    const el = createMockInput("text");
    const text = "anything goes here";
    expect(enforceMaxlength(el, text)).toBe(text);
  });

  it("returns text unchanged when within limit", () => {
    const el = createMockInput("text");
    el.setAttribute("maxlength", "20");
    expect(enforceMaxlength(el, "short")).toBe("short");
  });

  it("truncates at the last word boundary before the limit", () => {
    const el = createMockInput("text");
    el.setAttribute("maxlength", "15");
    const result = enforceMaxlength(el, "the quick brown fox jumps");
    expect(result.length).toBeLessThanOrEqual(15);
    // Should not end mid-word.
    expect(result.endsWith(" ")).toBe(false);
    expect(["the quick brown", "the quick"]).toContain(result);
  });

  it("hard-truncates when no usable word boundary exists", () => {
    const el = createMockInput("text");
    el.setAttribute("maxlength", "5");
    // Single long word: word boundary at index 0 is too early, hard cut.
    const result = enforceMaxlength(el, "supercalifragilistic");
    expect(result.length).toBe(5);
  });
});

describe("typeInto", () => {
  it("types each character with input events", async () => {
    const el = createMockInput("text");
    let inputs = 0;
    el.addEventListener("input", () => inputs++);
    await typeInto(el, "abc", 1, 3);
    // 1 clear + 3 chars = 4 input events
    expect(inputs).toBe(4);
    expect(el.value).toBe("abc");
  });

  it("dispatches change and blur at the end", async () => {
    const el = createMockInput("text");
    let changed = false;
    let blurred = false;
    el.addEventListener("change", () => (changed = true));
    el.addEventListener("blur", () => (blurred = true));
    await typeInto(el, "hi", 1, 2);
    expect(changed).toBe(true);
    expect(blurred).toBe(true);
  });

  it("respects maxlength", async () => {
    const el = createMockInput("text");
    el.setAttribute("maxlength", "3");
    await typeInto(el, "hello world", 1, 2);
    expect(el.value.length).toBeLessThanOrEqual(3);
  });
});
