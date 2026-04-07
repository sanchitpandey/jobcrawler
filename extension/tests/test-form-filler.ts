/**
 * Tests for form-filler.ts.
 * Run via `npm test` (vitest + jsdom).
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  fillTextField,
  fillTextarea,
  fillSelect,
  fillRadioGroup,
  fillCheckbox,
  fillField,
  fillAllFields,
  setNativeValue,
  matchOption,
} from "../src/content/form-filler.js";
import {
  createMockInput,
  createMockTextarea,
  createMockSelect,
  createMockRadioGroup,
  resetDom,
} from "./test-setup.js";
import type { ApiField, AnswerItem } from "../src/types/index.js";

beforeEach(resetDom);

function answer(label: string, value: string, overrides: Partial<AnswerItem> = {}): AnswerItem {
  return {
    label,
    value,
    source: "pattern",
    confidence: 1.0,
    is_manual_review: false,
    ...overrides,
  };
}

describe("setNativeValue", () => {
  it("uses the prototype native setter, not direct assignment", () => {
    const el = createMockInput("text");
    // Simulate React's value override that swallows direct assignments.
    let reactCaught = false;
    Object.defineProperty(el, "value", {
      set: () => {
        reactCaught = true;
      },
      get: () => "",
      configurable: true,
    });
    setNativeValue(el, "hello");
    // The React-style overridden setter must NOT have been triggered,
    // because we used the prototype's native setter directly.
    expect(reactCaught).toBe(false);
  });

  it("dispatches input and change events", () => {
    const el = createMockInput("text");
    const events: string[] = [];
    el.addEventListener("input", () => events.push("input"));
    el.addEventListener("change", () => events.push("change"));
    setNativeValue(el, "abc");
    expect(events).toEqual(["input", "change"]);
    expect(el.value).toBe("abc");
  });
});

describe("fillTextField", () => {
  it("sets the value and respects maxlength", async () => {
    const el = createMockInput("text");
    el.setAttribute("maxlength", "5");
    await fillTextField(el, "hello world");
    expect(el.value.length).toBeLessThanOrEqual(5);
  });
});

describe("fillTextarea", () => {
  it("sets value and dispatches events", async () => {
    const el = createMockTextarea();
    let saw = 0;
    el.addEventListener("input", () => saw++);
    await fillTextarea(el, "long answer");
    expect(el.value).toBe("long answer");
    expect(saw).toBe(1);
  });
});

describe("fillSelect", () => {
  it("matches option text exactly (case-insensitive)", async () => {
    const el = createMockSelect(["Yes", "No", "Maybe"]);
    await fillSelect(el, "no");
    expect(el.options[el.selectedIndex].textContent).toBe("No");
  });

  it("falls back to substring match", async () => {
    const el = createMockSelect(["Less than 1 year", "1-3 years", "3+ years"]);
    await fillSelect(el, "3");
    expect(el.options[el.selectedIndex].textContent).toContain("3");
  });

  it("uses notice-period semantic mapping", async () => {
    const el = createMockSelect([
      "Less than 15 Days",
      "15 Days",
      "30 Days",
      "45 Days",
    ]);
    await fillSelect(el, "Available immediately");
    expect(el.options[el.selectedIndex].textContent).toBe("Less than 15 Days");
  });

  it("dispatches change event for React", async () => {
    const el = createMockSelect(["Yes", "No"]);
    let changed = false;
    el.addEventListener("change", () => (changed = true));
    await fillSelect(el, "Yes");
    expect(changed).toBe(true);
  });
});

describe("fillRadioGroup", () => {
  it("clicks the matching radio by value", async () => {
    const fs = createMockRadioGroup("gender", ["Male", "Female", "Other"]);
    await fillRadioGroup(fs, "Female", ["Male", "Female", "Other"]);
    const checked = fs.querySelector<HTMLInputElement>(
      'input[type="radio"]:checked'
    );
    expect(checked?.value).toBe("Female");
  });

  it("falls back to label text matching", async () => {
    const fs = createMockRadioGroup("auth", ["Yes", "No"]);
    await fillRadioGroup(fs, "true", ["Yes", "No"]);
    const checked = fs.querySelector<HTMLInputElement>(
      'input[type="radio"]:checked'
    );
    expect(checked?.value).toBe("Yes");
  });
});

describe("fillCheckbox", () => {
  it("toggles to checked when desired", async () => {
    const el = createMockInput("checkbox");
    expect(el.checked).toBe(false);
    await fillCheckbox(el, true);
    expect(el.checked).toBe(true);
  });

  it("does not flip an already-correct checkbox", async () => {
    const el = createMockInput("checkbox");
    el.checked = true;
    let clicks = 0;
    el.addEventListener("click", () => clicks++);
    await fillCheckbox(el, true);
    expect(clicks).toBe(0);
  });
});

describe("fillField (dispatch by type)", () => {
  it("fills a text input by id", async () => {
    const el = createMockInput("text", "fname");
    const field: ApiField = {
      name: "fname",
      label: "First name",
      type: "text",
      id: "fname",
    };
    const result = await fillField(field, answer("First name", "Sanchit"));
    expect(result.success).toBe(true);
    expect(el.value).toBe("Sanchit");
  });

  it("skips manual review answers", async () => {
    createMockInput("text", "open");
    const field: ApiField = {
      name: "open",
      label: "Tell us about yourself",
      type: "text",
      id: "open",
    };
    const result = await fillField(
      field,
      answer("Tell us about yourself", "x", { is_manual_review: true })
    );
    expect(result.success).toBe(false);
    expect(result.error).toBe("manual_review");
  });

  it("returns element_not_found when DOM has no match", async () => {
    const field: ApiField = {
      name: "missing",
      label: "Missing",
      type: "text",
      id: "does_not_exist",
    };
    const result = await fillField(field, answer("Missing", "x"));
    expect(result.success).toBe(false);
    expect(result.error).toBe("element_not_found");
  });
});

describe("fillAllFields", () => {
  it("fills multiple fields and reports per-field results", async () => {
    createMockInput("text", "a");
    createMockInput("text", "b");
    const fields: ApiField[] = [
      { name: "a", label: "A", type: "text", id: "a" },
      { name: "b", label: "B", type: "text", id: "b" },
    ];
    const answers = [answer("A", "alpha"), answer("B", "beta")];
    const results = await fillAllFields(fields, answers);
    expect(results).toHaveLength(2);
    expect(results.every((r) => r.success)).toBe(true);
    expect((document.getElementById("a") as HTMLInputElement).value).toBe(
      "alpha"
    );
  }, 10_000);

  it("reports no_answer for fields with no matching label", async () => {
    createMockInput("text", "a");
    const fields: ApiField[] = [
      { name: "a", label: "A", type: "text", id: "a" },
    ];
    const results = await fillAllFields(fields, []);
    expect(results[0].error).toBe("no_answer");
  });
});

describe("matchOption (exported helper)", () => {
  it("handles boolean shorthands", () => {
    expect(matchOption("true", ["Yes", "No"])).toBe("Yes");
    expect(matchOption("0", ["Yes", "No"])).toBe("No");
  });

  it("returns null when nothing matches", () => {
    expect(matchOption("purple", ["red", "blue"])).toBeNull();
  });
});
