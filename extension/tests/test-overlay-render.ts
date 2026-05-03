/**
 * Tests for overlay rendering: score badge + review panel structure.
 * Run via `npm test` (vitest + jsdom).
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  showScoreBadge,
  showReviewPanel,
  removeOverlay,
  __getActiveShadowRoot,
} from "../src/overlay/overlay.js";
import { resetDom } from "./test-setup.js";
import type { ApiField, AnswerItem, ScoreResponse } from "../src/types/index.js";

beforeEach(() => {
  resetDom();
  removeOverlay();
});

function score(fit: number, overrides: Partial<ScoreResponse> = {}): ScoreResponse {
  return {
    fit_score: fit,
    verdict: "yes",
    comp_est: "$120k - $150k",
    gaps: ["No Kubernetes experience", "Limited Rust"],
    ...overrides,
  };
}

function field(label: string, type: string = "text"): ApiField {
  return { name: label.toLowerCase().replace(/\s+/g, "_"), label, type };
}

function answer(
  label: string,
  value: string,
  overrides: Partial<AnswerItem> = {},
): AnswerItem {
  return {
    label,
    value,
    source: "pattern",
    confidence: 1.0,
    is_manual_review: false,
    ...overrides,
  };
}

describe("showScoreBadge", () => {
  it("test_score_badge_renders: injects badge into shadow root", () => {
    showScoreBadge(score(87));
    const shadow = __getActiveShadowRoot();
    expect(shadow).not.toBeNull();
    const badge = shadow!.querySelector(".jc-badge");
    expect(badge).not.toBeNull();
    expect(badge!.textContent).toContain("87");
  });

  it("test_score_badge_colors: 87 → good (green)", () => {
    showScoreBadge(score(87));
    const circle = __getActiveShadowRoot()!.querySelector(".jc-badge-circle")!;
    expect(circle.classList.contains("jc-badge-circle--good")).toBe(true);
  });

  it("test_score_badge_colors: 55 → ok (amber)", () => {
    showScoreBadge(score(55));
    const circle = __getActiveShadowRoot()!.querySelector(".jc-badge-circle")!;
    expect(circle.classList.contains("jc-badge-circle--ok")).toBe(true);
  });

  it("test_score_badge_colors: 30 → poor (red)", () => {
    showScoreBadge(score(30));
    const circle = __getActiveShadowRoot()!.querySelector(".jc-badge-circle")!;
    expect(circle.classList.contains("jc-badge-circle--poor")).toBe(true);
  });

  it("renders gaps in expandable detail panel", () => {
    showScoreBadge(score(87));
    const detail = __getActiveShadowRoot()!.querySelector(".jc-badge-detail")!;
    expect(detail.textContent).toContain("Kubernetes");
    expect(detail.textContent).toContain("Rust");
  });
});

describe("showReviewPanel — rendering", () => {
  const jobInfo = {
    title: "ML Engineer",
    company: "Google",
    location: "Bengaluru",
    score: 87,
    verdict: "strong_yes",
  };

  it("test_review_panel_renders: shows all fields with values", () => {
    const fields = [field("Email"), field("Years of Python")];
    const answers = [answer("Email", "a@b.com"), answer("Years of Python", "3")];

    void showReviewPanel(jobInfo, fields, answers);

    const shadow = __getActiveShadowRoot()!;
    const inputs = shadow.querySelectorAll<HTMLInputElement>(".jc-field-value");
    expect(inputs.length).toBe(2);
    expect(inputs[0].value).toBe("a@b.com");
    expect(inputs[1].value).toBe("3");

    const labels = Array.from(
      shadow.querySelectorAll(".jc-field-label"),
    ).map((el) => el.textContent);
    expect(labels).toContain("Email");
    expect(labels).toContain("Years of Python");
  });

  it("test_field_confidence_indicators: pattern → green, llm → blue, review → amber", () => {
    const fields = [field("A"), field("B"), field("C")];
    const answers = [
      answer("A", "x", { source: "pattern" }),
      answer("B", "y", { source: "llm", confidence: 0.87 }),
      answer("C", "", { source: "manual_review", is_manual_review: true }),
    ];
    void showReviewPanel(jobInfo, fields, answers);

    const shadow = __getActiveShadowRoot()!;
    const pills = shadow.querySelectorAll(".jc-confidence");
    expect(pills.length).toBe(3);
    expect(pills[0].classList.contains("jc-confidence--pattern")).toBe(true);
    expect(pills[1].classList.contains("jc-confidence--ai")).toBe(true);
    expect(pills[1].textContent).toContain("87%");
    expect(pills[2].classList.contains("jc-confidence--review")).toBe(true);
  });

  it("test_manual_review_highlighted: review fields have amber wrapper class", () => {
    const fields = [field("Why fit?")];
    const answers = [
      answer("Why fit?", "", { source: "manual_review", is_manual_review: true }),
    ];
    void showReviewPanel(jobInfo, fields, answers);

    const fieldEl = __getActiveShadowRoot()!.querySelector(".jc-field")!;
    expect(fieldEl.classList.contains("jc-field--review")).toBe(true);
  });

  it("renders job summary header with company and title", () => {
    void showReviewPanel(jobInfo, [field("Email")], [answer("Email", "x@y.com")]);
    const shadow = __getActiveShadowRoot()!;
    expect(shadow.querySelector(".jc-job-title")!.textContent).toContain("ML Engineer");
    expect(shadow.querySelector(".jc-job-meta")!.textContent).toContain("Google");
  });

  it("renders summary footer counts", () => {
    const fields = [field("A"), field("B"), field("C")];
    const answers = [
      answer("A", "x", { source: "pattern" }),
      answer("B", "y", { source: "llm", confidence: 0.9 }),
      answer("C", "", { is_manual_review: true, source: "manual_review" }),
    ];
    void showReviewPanel(jobInfo, fields, answers);

    const summary = __getActiveShadowRoot()!.querySelector(".jc-summary")!;
    expect(summary.textContent).toContain("1 auto-filled");
    expect(summary.textContent).toContain("1 AI-generated");
    expect(summary.textContent).toContain("1 needs review");
  });
});
