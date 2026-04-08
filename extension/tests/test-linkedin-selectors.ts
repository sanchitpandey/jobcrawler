/**
 * Tests for the pure-DOM helpers in sites/linkedin.ts.
 * No chrome.runtime, no network — just selector classification on jsdom.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  extractJobInfo,
  findActionButton,
  detectErrors,
  hasFileUpload,
  isReviewStep,
  waitForFormReady,
} from "../src/content/sites/linkedin.js";
import { resetDom } from "./test-setup.js";

beforeEach(resetDom);

// ── Modal builders ────────────────────────────────────────────────────────────

function buildModal(innerHTML: string): HTMLElement {
  const modal = document.createElement("div");
  modal.className = "jobs-easy-apply-modal";
  modal.setAttribute("role", "dialog");
  modal.innerHTML = innerHTML;
  document.body.appendChild(modal);
  return modal;
}

function buildFooter(buttons: Array<{ text: string; primary?: boolean; disabled?: boolean; aria?: string }>): string {
  const html = buttons
    .map(
      (b) =>
        `<button class="${b.primary ? "artdeco-button--primary" : "artdeco-button--secondary"}"${
          b.disabled ? " disabled" : ""
        }${b.aria ? ` aria-label="${b.aria}"` : ""}>${b.text}</button>`,
    )
    .join("");
  return `<div class="jobs-easy-apply-modal__footer">${html}</div>`;
}

// ── extractJobInfo ────────────────────────────────────────────────────────────

describe("extractJobInfo", () => {
  it("pulls title/company/location/description from the listing page", () => {
    document.body.innerHTML = `
      <h1 class="t-24">Senior ML Engineer</h1>
      <div class="jobs-unified-top-card__company-name"><a href="/c/acme">Acme Corp</a></div>
      <span class="jobs-unified-top-card__bullet">Bengaluru, India</span>
      <div class="jobs-description__content">Build models. Deploy them. PyTorch.</div>
    `;
    const info = extractJobInfo();
    expect(info.title).toBe("Senior ML Engineer");
    expect(info.company).toBe("Acme Corp");
    expect(info.location).toBe("Bengaluru, India");
    expect(info.description).toContain("PyTorch");
    expect(info.url).toBe(window.location.href);
  });

  it("falls back to alternate selectors", () => {
    document.body.innerHTML = `
      <h1 class="job-details-jobs-unified-top-card__job-title">Backend Dev</h1>
      <div class="job-details-jobs-unified-top-card__company-name">Globex</div>
      <div id="job-details">Go. Postgres.</div>
    `;
    const info = extractJobInfo();
    expect(info.title).toBe("Backend Dev");
    expect(info.company).toBe("Globex");
    expect(info.description).toContain("Go");
  });

  it("returns empty strings when nothing matches", () => {
    document.body.innerHTML = "<div>nothing here</div>";
    const info = extractJobInfo();
    expect(info.title).toBe("");
    expect(info.company).toBe("");
    expect(info.description).toBe("");
  });
});

// ── findActionButton ──────────────────────────────────────────────────────────

describe("findActionButton", () => {
  it("classifies a Next button", () => {
    const modal = buildModal(buildFooter([{ text: "Next", primary: true }]));
    const action = findActionButton(modal);
    expect(action?.action).toBe("next");
  });

  it("classifies a Review button", () => {
    const modal = buildModal(buildFooter([{ text: "Review", primary: true }]));
    expect(findActionButton(modal)?.action).toBe("review");
  });

  it("classifies a Submit application button", () => {
    const modal = buildModal(buildFooter([{ text: "Submit application", primary: true }]));
    expect(findActionButton(modal)?.action).toBe("submit");
  });

  it("prefers aria-label over text", () => {
    const modal = buildModal(
      buildFooter([{ text: "Continue", primary: true, aria: "Submit application" }]),
    );
    expect(findActionButton(modal)?.action).toBe("submit");
  });

  it("skips disabled buttons", () => {
    const modal = buildModal(
      buildFooter([
        { text: "Next", primary: true, disabled: true },
        { text: "Submit application", primary: true },
      ]),
    );
    expect(findActionButton(modal)?.action).toBe("submit");
  });

  it("returns null when no buttons exist", () => {
    const modal = buildModal("<div></div>");
    expect(findActionButton(modal)).toBeNull();
  });
});

// ── detectErrors ──────────────────────────────────────────────────────────────

describe("detectErrors", () => {
  it("extracts inline error messages", () => {
    const modal = buildModal(`
      <div class="jobs-easy-apply-form-section__grouping">
        <label>Years of experience</label>
        <input type="text" />
        <div class="artdeco-inline-feedback--error">
          <span class="artdeco-inline-feedback__message">Enter a whole number</span>
        </div>
      </div>
    `);
    const errors = detectErrors(modal);
    expect(errors).toHaveLength(1);
    expect(errors[0].errorMessage).toBe("Enter a whole number");
    expect(errors[0].fieldLabel).toBe("Years of experience");
  });

  it("dedups repeat errors and ignores empty ones", () => {
    const modal = buildModal(`
      <div class="jobs-easy-apply-form-section__grouping">
        <label>Phone</label>
        <span class="artdeco-inline-feedback__message"></span>
        <div role="alert">Required</div>
      </div>
    `);
    const errors = detectErrors(modal);
    expect(errors).toHaveLength(1);
    expect(errors[0].errorMessage).toBe("Required");
  });

  it("returns [] when there are no errors", () => {
    const modal = buildModal("<div><label>Name</label><input /></div>");
    expect(detectErrors(modal)).toEqual([]);
  });
});

// ── hasFileUpload / isReviewStep ──────────────────────────────────────────────

describe("hasFileUpload", () => {
  it("detects a resume input", () => {
    const modal = buildModal('<input type="file" />');
    expect(hasFileUpload(modal)).toBe(true);
  });

  it("returns false without a file input", () => {
    const modal = buildModal('<input type="text" />');
    expect(hasFileUpload(modal)).toBe(false);
  });
});

describe("isReviewStep", () => {
  it("returns true when there are no editable fields and a review summary", () => {
    const modal = buildModal(
      '<div class="jobs-easy-apply-content__review">Review your application</div>',
    );
    expect(isReviewStep(modal)).toBe(true);
  });

  it("returns true based on the 'Review your application' text heuristic", () => {
    const modal = buildModal("<div>Review your application before submitting.</div>");
    expect(isReviewStep(modal)).toBe(true);
  });

  it("returns false when there are editable fields", () => {
    const modal = buildModal('<input type="text" />');
    expect(isReviewStep(modal)).toBe(false);
  });
});

// ── waitForFormReady ──────────────────────────────────────────────────────────

describe("waitForFormReady", () => {
  it("resolves immediately if a field is already present", async () => {
    const modal = buildModal('<input type="text" />');
    await expect(waitForFormReady(modal, 200)).resolves.toBe(modal);
  });

  it("resolves once a field is added asynchronously", async () => {
    const modal = buildModal("<div></div>");
    setTimeout(() => {
      const input = document.createElement("input");
      input.type = "text";
      modal.appendChild(input);
    }, 20);
    await expect(waitForFormReady(modal, 500)).resolves.toBe(modal);
  });

  it("rejects on timeout", async () => {
    const modal = buildModal("<div></div>");
    await expect(waitForFormReady(modal, 50)).rejects.toThrow(/timeout/);
  });
});
