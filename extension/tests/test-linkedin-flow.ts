/**
 * Tests for the multi-step Easy Apply orchestration in sites/linkedin.ts.
 *
 * Mocks chrome.runtime.sendMessage so we can drive handleStep / handleEasyApply
 * end-to-end against jsdom-built modals.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import type { Message, AnswerItem } from "../src/types/index.js";
import { resetDom } from "./test-setup.js";

// ── chrome.runtime stub ───────────────────────────────────────────────────────

interface ChromeStub {
  runtime: {
    sendMessage: (msg: Message, cb: (resp: unknown) => void) => void;
    lastError?: { message: string };
  };
}

let answerHandler: (fields: { label: string; type: string }[]) => AnswerItem[];
let trackJobCalls: number;
let updateStatusCalls: Array<{ status: string }>;

beforeEach(() => {
  resetDom();
  trackJobCalls = 0;
  updateStatusCalls = [];
  answerHandler = (fields) =>
    fields.map((f) => ({
      label: f.label,
      value: `auto-${f.label}`,
      source: "pattern",
      confidence: 1.0,
      is_manual_review: false,
    }));

  const stub: ChromeStub = {
    runtime: {
      sendMessage: (msg, cb) => {
        queueMicrotask(() => {
          switch (msg.type) {
            case "SCORE_JOB":
              cb({
                type: "SCORE_JOB_RESULT",
                payload: { fit_score: 80, verdict: "good", comp_est: null, gaps: [] },
              });
              return;
            case "TRACK_JOB":
              trackJobCalls += 1;
              cb({ type: "TRACK_JOB_RESULT", payload: { app_id: "app-123" } });
              return;
            case "UPDATE_STATUS":
              updateStatusCalls.push({ status: msg.payload.status });
              cb({ type: "UPDATE_STATUS_RESULT", payload: { ok: true } });
              return;
            case "ANSWER_FIELDS": {
              const answers = answerHandler(
                msg.payload.fields.map((f) => ({ label: f.label, type: f.type })),
              );
              cb({ type: "ANSWER_FIELDS_RESULT", payload: { answers } });
              return;
            }
            default:
              cb({ type: "ERROR", payload: { message: "unhandled" } });
          }
        });
      },
    },
  };
  (globalThis as unknown as { chrome: ChromeStub }).chrome = stub;
});

// Speed up tests: stub the human-delay module before importing linkedin.ts.
vi.mock("../src/content/human-delay.js", () => ({
  humanDelay: () => Promise.resolve(),
  humanType: (el: HTMLInputElement | HTMLTextAreaElement, value: string) => {
    el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return Promise.resolve();
  },
  enforceMaxlength: (el: HTMLInputElement | HTMLTextAreaElement, value: string) => {
    const max = el.getAttribute("maxlength");
    if (max) {
      const n = parseInt(max, 10);
      if (!Number.isNaN(n)) return value.slice(0, n);
    }
    return value;
  },
}));

// Stub the overlay so it doesn't try to mount UI. The review panel is mocked
// to auto-approve all answers (mirrors clicking "Submit Application").
vi.mock("../src/overlay/overlay.js", () => ({
  showOverlay: () => undefined,
  hideOverlay: () => undefined,
  showScoreBadge: () => undefined,
  removeOverlay: () => undefined,
  removePanel: () => undefined,
  showReviewPanel: (
    _job: unknown,
    _fields: { label: string }[],
    answers: { label: string; value: string }[],
  ) =>
    Promise.resolve(
      answers.map((a) => ({ label: a.label, value: a.value, approved: true })),
    ),
}));

import {
  handleStep,
  handleEasyApply,
} from "../src/content/sites/linkedin.js";

// ── Modal builders ────────────────────────────────────────────────────────────

function buildModalWithFields(
  fields: Array<{ id: string; label: string; type?: string }>,
  buttonText: string = "Next",
): HTMLElement {
  const modal = document.createElement("div");
  modal.className = "jobs-easy-apply-modal";
  const form = document.createElement("form");
  for (const f of fields) {
    const grouping = document.createElement("div");
    grouping.className = "jobs-easy-apply-form-section__grouping";
    const label = document.createElement("label");
    label.setAttribute("for", f.id);
    label.textContent = f.label;
    const input = document.createElement("input");
    input.type = f.type ?? "text";
    input.id = f.id;
    input.name = f.id;
    grouping.appendChild(label);
    grouping.appendChild(input);
    form.appendChild(grouping);
  }
  modal.appendChild(form);
  const footer = document.createElement("div");
  footer.className = "jobs-easy-apply-modal__footer";
  const btn = document.createElement("button");
  btn.className = "artdeco-button--primary";
  btn.textContent = buttonText;
  footer.appendChild(btn);
  modal.appendChild(footer);
  document.body.appendChild(modal);
  return modal;
}

function buildJobPage(): void {
  const meta = document.createElement("div");
  meta.innerHTML = `
    <h1 class="t-24">SWE Intern</h1>
    <div class="jobs-unified-top-card__company-name"><a>Acme</a></div>
    <span class="jobs-unified-top-card__bullet">Remote</span>
    <div class="jobs-description__content">Cool job.</div>
  `;
  document.body.appendChild(meta);
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe("handleStep — single step fill", () => {
  it("fills all fields and reports the action", async () => {
    const modal = buildModalWithFields(
      [
        { id: "fname", label: "First name" },
        { id: "phone", label: "Phone" },
      ],
      "Next",
    );
    const ctx = {
      modal,
      jobInfo: { title: "t", company: "c", location: "l", description: "d", url: "u" },
      filledFields: {} as Record<string, string>,
    };
    const action = await handleStep(modal, ctx);
    expect(action).toBe("next");
    expect((document.getElementById("fname") as HTMLInputElement).value).toBe("auto-First name");
    expect((document.getElementById("phone") as HTMLInputElement).value).toBe("auto-Phone");
    expect(ctx.filledFields["First name"]).toBe("auto-First name");
  });
});

describe("handleStep — skip pre-filled fields", () => {
  it("does not overwrite a field that already has a value", async () => {
    const modal = buildModalWithFields([{ id: "fname", label: "First name" }]);
    (document.getElementById("fname") as HTMLInputElement).value = "Already";

    let answered = 0;
    answerHandler = (fields) => {
      answered = fields.length;
      return fields.map((f) => ({
        label: f.label,
        value: "should-not-apply",
        source: "pattern",
        confidence: 1.0,
        is_manual_review: false,
      }));
    };

    const ctx = {
      modal,
      jobInfo: { title: "t", company: "c", location: "l", description: "d", url: "u" },
      filledFields: {} as Record<string, string>,
    };
    await handleStep(modal, ctx);
    // The pre-filled field should be filtered out before the API call.
    expect(answered).toBe(0);
    expect((document.getElementById("fname") as HTMLInputElement).value).toBe("Already");
  });
});

describe("handleStep — file upload only", () => {
  it("skips filling and returns next when only a file input is present", async () => {
    const modal = document.createElement("div");
    modal.className = "jobs-easy-apply-modal";
    const form = document.createElement("form");
    const file = document.createElement("input");
    file.type = "file";
    form.appendChild(file);
    modal.appendChild(form);
    const footer = document.createElement("div");
    footer.className = "jobs-easy-apply-modal__footer";
    const btn = document.createElement("button");
    btn.className = "artdeco-button--primary";
    btn.textContent = "Next";
    footer.appendChild(btn);
    modal.appendChild(footer);
    document.body.appendChild(modal);

    let called = 0;
    answerHandler = (f) => {
      called += 1;
      return [];
    };

    const ctx = {
      modal,
      jobInfo: { title: "t", company: "c", location: "l", description: "d", url: "u" },
      filledFields: {} as Record<string, string>,
    };
    const action = await handleStep(modal, ctx);
    expect(action).toBe("next");
    expect(called).toBe(0);
  });
});

describe("handleStep — review step", () => {
  it("does not scan or fill on a review summary step", async () => {
    const modal = document.createElement("div");
    modal.className = "jobs-easy-apply-modal";
    modal.innerHTML = `
      <div class="jobs-easy-apply-content__review">Review your application</div>
      <div class="jobs-easy-apply-modal__footer">
        <button class="artdeco-button--primary">Submit application</button>
      </div>
    `;
    document.body.appendChild(modal);

    let called = 0;
    answerHandler = () => {
      called += 1;
      return [];
    };

    const ctx = {
      modal,
      jobInfo: { title: "t", company: "c", location: "l", description: "d", url: "u" },
      filledFields: {} as Record<string, string>,
    };
    const action = await handleStep(modal, ctx);
    expect(action).toBe("submit");
    expect(called).toBe(0);
  });
});

describe("handleStep — error retry", () => {
  it("re-requests answers when validation errors appear after fill", async () => {
    const modal = buildModalWithFields([{ id: "yrs", label: "Years" }]);
    // Inject an error message into the field's grouping so detectErrors fires.
    const grouping = modal.querySelector(".jobs-easy-apply-form-section__grouping")!;
    const err = document.createElement("div");
    err.className = "artdeco-inline-feedback--error";
    err.innerHTML =
      '<span class="artdeco-inline-feedback__message">Enter a whole number</span>';
    grouping.appendChild(err);

    let answerCalls = 0;
    answerHandler = (fields) => {
      answerCalls += 1;
      return fields.map((f) => ({
        label: f.label,
        value: answerCalls === 1 ? "two" : "2",
        source: "pattern",
        confidence: 1.0,
        is_manual_review: false,
      }));
    };

    const ctx = {
      modal,
      jobInfo: { title: "t", company: "c", location: "l", description: "d", url: "u" },
      filledFields: {} as Record<string, string>,
    };
    await handleStep(modal, ctx);
    expect(answerCalls).toBe(2);
    expect((document.getElementById("yrs") as HTMLInputElement).value).toBe("2");
  });
});

describe("handleEasyApply — multi-step navigation", () => {
  it("walks Next → Review → Submit and tracks the job", async () => {
    buildJobPage();

    // Step 1: one field, primary button "Next".
    const modal = buildModalWithFields([{ id: "fname", label: "First name" }], "Next");

    // After we click Next, swap the form to step 2 (Review).
    const originalClick = HTMLButtonElement.prototype.click;
    let stepIndex = 0;
    HTMLButtonElement.prototype.click = function () {
      stepIndex += 1;
      // Mutate the modal: replace its contents with the next step.
      if (stepIndex === 1) {
        modal.innerHTML = `
          <form>
            <div class="jobs-easy-apply-form-section__grouping">
              <label for="why">Why us?</label>
              <input id="why" type="text" />
            </div>
          </form>
          <div class="jobs-easy-apply-modal__footer">
            <button class="artdeco-button--primary">Review</button>
          </div>
        `;
      } else if (stepIndex === 2) {
        modal.innerHTML = `
          <div class="jobs-easy-apply-content__review">Review your application</div>
          <div class="jobs-easy-apply-modal__footer">
            <button class="artdeco-button--primary">Submit application</button>
          </div>
        `;
      }
    };

    try {
      const result = await handleEasyApply(modal);
      expect(result.success).toBe(true);
      // Steps: fill -> Next, fill -> Review, then Submit step (no click).
      expect(result.stepsCompleted).toBeGreaterThanOrEqual(3);
      expect(trackJobCalls).toBe(1);
      // We should have transitioned to "applying" on submit-ready.
      expect(updateStatusCalls.some((c) => c.status === "applying")).toBe(true);
    } finally {
      HTMLButtonElement.prototype.click = originalClick;
    }
  });
});
