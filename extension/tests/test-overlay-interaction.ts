/**
 * Tests for overlay interaction: edit, submit, skip, keyboard.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  showReviewPanel,
  removeOverlay,
  __getActiveShadowRoot,
} from "../src/overlay/overlay.js";
import { resetDom } from "./test-setup.js";
import type { ApiField, AnswerItem } from "../src/types/index.js";

beforeEach(() => {
  resetDom();
  removeOverlay();
});

const jobInfo = {
  title: "ML Engineer",
  company: "Google",
  location: "Bengaluru",
  score: 87,
  verdict: "yes",
};

function field(label: string): ApiField {
  return { name: label.toLowerCase(), label, type: "text" };
}

function answer(label: string, value: string, partial: Partial<AnswerItem> = {}): AnswerItem {
  return {
    label,
    value,
    source: "pattern",
    confidence: 1.0,
    is_manual_review: false,
    ...partial,
  };
}

describe("showReviewPanel — interaction", () => {
  it("test_submit_returns_answers", async () => {
    const fields = [field("Email"), field("Phone")];
    const answers = [answer("Email", "a@b.com"), answer("Phone", "555")];
    const promise = showReviewPanel(jobInfo, fields, answers);

    const shadow = __getActiveShadowRoot()!;
    const submitBtn = shadow.querySelector<HTMLButtonElement>('[data-jc="submit"]')!;
    submitBtn.click();

    const result = await promise;
    expect(result).not.toBeNull();
    expect(result!.length).toBe(2);
    expect(result![0]).toEqual({ label: "Email", value: "a@b.com", approved: true });
    expect(result![1]).toEqual({ label: "Phone", value: "555", approved: true });
  });

  it("test_edit_field: user-edited value is reflected in result", async () => {
    const fields = [field("Email")];
    const answers = [answer("Email", "old@x.com")];
    const promise = showReviewPanel(jobInfo, fields, answers);

    const shadow = __getActiveShadowRoot()!;
    const input = shadow.querySelector<HTMLInputElement>(".jc-field-value")!;
    input.value = "new@x.com";

    shadow.querySelector<HTMLButtonElement>('[data-jc="submit"]')!.click();
    const result = await promise;
    expect(result![0].value).toBe("new@x.com");
  });

  it("test_skip_returns_null", async () => {
    const promise = showReviewPanel(
      jobInfo,
      [field("Email")],
      [answer("Email", "a@b.com")],
    );
    __getActiveShadowRoot()!
      .querySelector<HTMLButtonElement>('[data-jc="skip"]')!
      .click();
    const result = await promise;
    expect(result).toBeNull();
  });

  it("test_escape_closes: Escape key resolves null", async () => {
    const promise = showReviewPanel(
      jobInfo,
      [field("Email")],
      [answer("Email", "a@b.com")],
    );
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    const result = await promise;
    expect(result).toBeNull();
  });

  it("test_ctrl_enter_submits: Ctrl+Enter resolves with answers", async () => {
    const promise = showReviewPanel(
      jobInfo,
      [field("Email")],
      [answer("Email", "a@b.com")],
    );
    window.dispatchEvent(
      new KeyboardEvent("keydown", { key: "Enter", ctrlKey: true }),
    );
    const result = await promise;
    expect(result).not.toBeNull();
    expect(result![0].value).toBe("a@b.com");
  });

  it("backdrop click resolves null", async () => {
    const promise = showReviewPanel(
      jobInfo,
      [field("Email")],
      [answer("Email", "a@b.com")],
    );
    __getActiveShadowRoot()!
      .querySelector<HTMLElement>('[data-jc="backdrop"]')!
      .click();
    const result = await promise;
    expect(result).toBeNull();
  });
});
