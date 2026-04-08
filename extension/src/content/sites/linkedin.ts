/**
 * linkedin.ts — LinkedIn Easy Apply handler.
 *
 * Drives the multi-step Easy Apply modal end-to-end:
 *   extract job info → score → request answers → user review → fill → click
 *   Next/Review/Submit → repeat for each step → track applied state.
 *
 * Pure DOM only (no Playwright). Service worker handles all network I/O.
 */

import { scanFields } from "../field-scanner.js";
import { fillAllFields } from "../form-filler.js";
import {
  showScoreBadge,
  showReviewPanel,
  removeOverlay,
} from "../../overlay/overlay.js";
import { humanDelay } from "../human-delay.js";
import type {
  AnswerItem,
  ApiField,
  Message,
  ScoreResponse,
  TrackJobResponse,
} from "../../types/index.js";

// ── Selectors ─────────────────────────────────────────────────────────────────

const JOB_DESC_SELECTORS = [
  "div.jobs-description__content",
  ".jobs-description-content__text",
  "#job-details",
  ".jobs-description",
  "[data-test-job-description]",
] as const;

const SUBMIT_LABEL_RE = /submit application/i;
const REVIEW_LABEL_RE = /^review/i;
const NEXT_LABEL_RE = /^(next|continue)/i;

// ── Promisified chrome.runtime.sendMessage ────────────────────────────────────

function sendMessage<T>(message: Message): Promise<T> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response: T) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message ?? "sendMessage failed"));
        return;
      }
      resolve(response);
    });
  });
}

// ── Job info extraction ───────────────────────────────────────────────────────

export interface JobInfo {
  title: string;
  company: string;
  location: string;
  description: string;
  url: string;
}

function pickText(selectors: readonly string[]): string {
  for (const sel of selectors) {
    const el = document.querySelector(sel);
    const text = el?.textContent?.trim();
    if (text) return text;
  }
  return "";
}

/** Extract job listing metadata from the LinkedIn job page. */
export function extractJobInfo(): JobInfo {
  const title = pickText([
    "h1.t-24",
    "h1.jobs-unified-top-card__job-title",
    ".job-details-jobs-unified-top-card__job-title",
    "h1.jobs-details-top-card__job-title",
  ]);
  const company = pickText([
    ".jobs-unified-top-card__company-name a",
    ".jobs-unified-top-card__company-name",
    ".job-details-jobs-unified-top-card__company-name a",
    ".job-details-jobs-unified-top-card__company-name",
  ]);
  const location = pickText([
    ".jobs-unified-top-card__bullet",
    ".job-details-jobs-unified-top-card__bullet",
    ".jobs-unified-top-card__primary-description-container .tvm__text:first-child",
  ]);
  const description = pickText(JOB_DESC_SELECTORS);

  return { title, company, location, description, url: window.location.href };
}

// ── Form-ready waiter ─────────────────────────────────────────────────────────

const FORM_FIELD_SELECTOR =
  'input:not([type="hidden"]):not([type="file"]), select, textarea, [role="radiogroup"], [role="combobox"]';

/**
 * Wait until the modal contains at least one fillable field, OR until the
 * modal looks like a review/submit step (no fields, but a primary action).
 */
export async function waitForFormReady(
  modal: Element,
  timeoutMs: number = 5000,
): Promise<Element> {
  const isReady = (): boolean => {
    if (modal.querySelector(FORM_FIELD_SELECTOR)) return true;
    // Review steps have no fields but DO have a primary action button.
    if (modal.querySelector("button.artdeco-button--primary")) return true;
    return false;
  };

  if (isReady()) return modal;

  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      observer.disconnect();
      reject(new Error("waitForFormReady: timeout"));
    }, timeoutMs);

    const observer = new MutationObserver(() => {
      if (isReady()) {
        clearTimeout(timer);
        observer.disconnect();
        resolve(modal);
      }
    });
    observer.observe(modal, { childList: true, subtree: true });
  });
}

// ── Action button classification ─────────────────────────────────────────────

export type ActionType = "next" | "review" | "submit" | "unknown" | "skip";

export interface ActionButton {
  element: HTMLButtonElement;
  action: ActionType;
}

function classifyButton(text: string, ariaLabel: string): ActionType {
  const probe = (s: string): ActionType | null => {
    const t = s.trim();
    if (!t) return null;
    if (SUBMIT_LABEL_RE.test(t)) return "submit";
    if (REVIEW_LABEL_RE.test(t)) return "review";
    if (NEXT_LABEL_RE.test(t)) return "next";
    return null;
  };
  return probe(ariaLabel) ?? probe(text) ?? "unknown";
}

/** Find the primary action button in the modal footer. */
export function findActionButton(modal: Element): ActionButton | null {
  const candidates = Array.from(
    modal.querySelectorAll<HTMLButtonElement>(
      "button.artdeco-button--primary, footer button[data-easy-apply-next-button], footer button[aria-label]",
    ),
  );
  // Prefer buttons inside the footer if any.
  const footer =
    modal.querySelector(".jobs-easy-apply-modal__footer") ??
    modal.querySelector("footer");
  const ordered = footer
    ? [
        ...Array.from(
          footer.querySelectorAll<HTMLButtonElement>("button.artdeco-button--primary, button"),
        ),
        ...candidates,
      ]
    : candidates;

  for (const btn of ordered) {
    if (btn.disabled) continue;
    const text = btn.textContent ?? "";
    const aria = btn.getAttribute("aria-label") ?? "";
    const action = classifyButton(text, aria);
    if (action !== "unknown") return { element: btn, action };
  }

  // Fallback: first enabled primary button — caller can decide what to do.
  const first = ordered.find((b) => !b.disabled);
  return first ? { element: first, action: "unknown" } : null;
}

// ── Error detection ───────────────────────────────────────────────────────────

export interface FieldError {
  fieldLabel: string;
  errorMessage: string;
}

const ERROR_SELECTORS = [
  ".artdeco-inline-feedback--error .artdeco-inline-feedback__message",
  ".fb-dash-form-element__error-field",
  '[id$="-error"]',
  '[role="alert"]',
] as const;

function nearestLabel(errEl: Element): string {
  const grouping =
    errEl.closest(".jobs-easy-apply-form-section__grouping") ??
    errEl.closest(".fb-dash-form-element") ??
    errEl.closest("fieldset") ??
    errEl.parentElement;
  if (!grouping) return "";
  const lbl =
    grouping.querySelector("label") ??
    grouping.querySelector("legend") ??
    grouping.querySelector(".artdeco-text-input--label");
  return (lbl?.textContent ?? "").trim();
}

/** Extract validation error messages from the current step. */
export function detectErrors(modal: Element): FieldError[] {
  const errors: FieldError[] = [];
  const seen = new Set<string>();
  for (const sel of ERROR_SELECTORS) {
    for (const el of Array.from(modal.querySelectorAll(sel))) {
      const msg = (el.textContent ?? "").trim();
      if (!msg) continue;
      const key = `${el.id}::${msg}`;
      if (seen.has(key)) continue;
      seen.add(key);
      errors.push({ fieldLabel: nearestLabel(el), errorMessage: msg });
    }
  }
  return errors;
}

// ── Step shape detection ─────────────────────────────────────────────────────

/** True if the current step contains a file upload (resume) input. */
export function hasFileUpload(modal: Element): boolean {
  return !!modal.querySelector('input[type="file"]');
}

/** True if the modal shows a review/confirmation page (no editable fields). */
export function isReviewStep(modal: Element): boolean {
  const editable = modal.querySelector(
    'input:not([type="hidden"]):not([type="file"]):not([type="button"]):not([type="submit"]), select, textarea',
  );
  if (editable) return false;
  // Heuristic: review summaries usually contain "Review your application" text
  // or a known summary container.
  if (modal.querySelector(".jobs-easy-apply-content__review")) return true;
  const text = (modal.textContent ?? "").toLowerCase();
  return text.includes("review your application");
}

// ── Helpers for skipping pre-filled fields ───────────────────────────────────

function elementHasValue(field: ApiField): boolean {
  const id = field.id;
  if (id) {
    const el = document.getElementById(id) as
      | HTMLInputElement
      | HTMLSelectElement
      | HTMLTextAreaElement
      | null;
    if (el && "value" in el && (el.value ?? "").trim() !== "") return true;
    if (el instanceof HTMLInputElement && (el.type === "checkbox" || el.type === "radio") && el.checked) return true;
  }
  if (field.type === "radio" && field.name) {
    const checked = document.querySelector<HTMLInputElement>(
      `input[type="radio"][name="${CSS.escape(field.name)}"]:checked`,
    );
    if (checked) return true;
  }
  return false;
}

// ── Step handler ─────────────────────────────────────────────────────────────

interface StepContext {
  modal: Element;
  jobInfo: JobInfo;
  filledFields: Record<string, string>;
  score?: ScoreResponse | null;
}

/**
 * Apply user edits from the review panel back onto the answer list.
 * Pairs by label; unmatched answers pass through unchanged.
 */
function mergeApprovedAnswers(
  original: AnswerItem[],
  approved: { label: string; value: string; approved: boolean }[],
): AnswerItem[] {
  const editsByLabel = new Map(approved.map((a) => [a.label, a]));
  return original.map((a) => {
    const edit = editsByLabel.get(a.label);
    if (!edit || !edit.approved) return a;
    if (edit.value === a.value) return a;
    // User-edited values are treated as fully trusted patterns.
    return {
      ...a,
      value: edit.value,
      source: "pattern",
      confidence: 1.0,
      is_manual_review: false,
    };
  });
}

async function requestAnswers(
  fields: ApiField[],
  jobInfo: JobInfo,
): Promise<AnswerItem[]> {
  const result = await sendMessage<{ type: string; payload?: { answers: AnswerItem[] }; message?: string }>({
    type: "ANSWER_FIELDS",
    payload: { fields, company: jobInfo.company, jobTitle: jobInfo.title },
  });
  if (result?.type !== "ANSWER_FIELDS_RESULT" || !result.payload) {
    throw new Error(`ANSWER_FIELDS failed: ${result?.message ?? "unknown error"}`);
  }
  return result.payload.answers ?? [];
}

/**
 * Handle one step of the Easy Apply modal: scan, request answers, fill,
 * locate the action button, and return its type so the caller can navigate.
 */
export async function handleStep(
  modal: Element,
  ctx: StepContext,
): Promise<ActionType> {
  await waitForFormReady(modal).catch(() => undefined);

  // Review step → no fill, just navigate.
  if (isReviewStep(modal)) {
    const action = findActionButton(modal);
    return action?.action ?? "unknown";
  }

  let fields = scanFields(modal);

  // File upload step with no other fields → skip filling, go to next.
  if (fields.length === 0 && hasFileUpload(modal)) {
    const action = findActionButton(modal);
    return action?.action ?? "next";
  }

  // Drop pre-filled fields so we don't overwrite the user's manual edits.
  const fillable = fields.filter((f) => !elementHasValue(f));

  if (fillable.length > 0) {
    const initialAnswers = await requestAnswers(fillable, ctx.jobInfo);

    // ── Review gate: show user every answer before touching the form. ──
    const approved = await showReviewPanel(
      {
        title: ctx.jobInfo.title,
        company: ctx.jobInfo.company,
        location: ctx.jobInfo.location,
        score: ctx.score?.fit_score,
        verdict: ctx.score?.verdict,
      },
      fillable,
      initialAnswers,
    );
    removeOverlay();

    if (approved === null) {
      return "skip";
    }

    const answers = mergeApprovedAnswers(initialAnswers, approved);
    const results = await fillAllFields(fillable, answers, modal);

    // Audit trail for tracker.
    for (const a of answers) {
      if (a.value && !a.is_manual_review) {
        ctx.filledFields[a.label] = a.value;
      }
    }

    const failed = results.filter((r) => !r.success);
    if (failed.length) {
      console.warn(
        `[JobCrawler:linkedin] ${failed.length}/${results.length} fields not filled:`,
        failed,
      );
    }

    // Brief settle delay before clicking Next.
    await humanDelay(400, 800);

    // Detect validation errors and retry once with error context.
    const errors = detectErrors(modal);
    if (errors.length > 0) {
      console.warn("[JobCrawler:linkedin] validation errors detected, retrying:", errors);
      const errorMap = new Map(errors.map((e) => [e.fieldLabel, e.errorMessage]));
      const retryFields: ApiField[] = fillable.map((f) => ({
        ...f,
        error: errorMap.get(f.label) ?? f.error,
      }));
      const retryAnswers = await requestAnswers(retryFields, ctx.jobInfo);
      await fillAllFields(retryFields, retryAnswers, modal);
      for (const a of retryAnswers) {
        if (a.value && !a.is_manual_review) {
          ctx.filledFields[a.label] = a.value;
        }
      }
      await humanDelay(400, 800);
    }
  }

  const action = findActionButton(modal);
  return action?.action ?? "unknown";
}

// ── Modal lifecycle helpers ──────────────────────────────────────────────────

function isModalAttached(modal: Element): boolean {
  return modal.isConnected && document.body.contains(modal);
}

async function waitForStepTransition(modal: Element, prevSnapshot: string): Promise<void> {
  // After clicking Next, LinkedIn animates a swap of the form contents.
  // Wait until the inner form HTML changes OR until form is ready again.
  const start = Date.now();
  const timeoutMs = 6000;
  while (Date.now() - start < timeoutMs) {
    await humanDelay(150, 250);
    if (!isModalAttached(modal)) return;
    const snap = (modal.querySelector("form")?.innerHTML ?? "").slice(0, 2000);
    if (snap !== prevSnapshot) {
      await waitForFormReady(modal).catch(() => undefined);
      return;
    }
  }
}

// ── Main entry point ─────────────────────────────────────────────────────────

export interface ApplyResult {
  success: boolean;
  stepsCompleted: number;
  error?: string;
}

const MAX_STEPS = 10;

/** Drive the entire Easy Apply flow for `modal`. */
export async function handleEasyApply(modal: Element): Promise<ApplyResult> {
  const jobInfo = extractJobInfo();
  console.log("[JobCrawler:linkedin] Easy Apply started:", jobInfo);

  // 1. Score the job (best-effort) and show overlay.
  let score: ScoreResponse | null = null;
  try {
    const result = await sendMessage<{ type: string; payload: ScoreResponse }>({
      type: "SCORE_JOB",
      payload: {
        title: jobInfo.title,
        company: jobInfo.company,
        description: jobInfo.description,
        url: jobInfo.url,
      },
    });
    if (result?.type === "SCORE_JOB_RESULT") {
      score = result.payload;
      showScoreBadge(score);
    }
  } catch (err) {
    console.warn("[JobCrawler:linkedin] SCORE_JOB failed:", err);
  }

  // 2. Track the job (creates Application row, returns app_id).
  let appId: string | null = null;
  try {
    const result = await sendMessage<{ type: string; payload: TrackJobResponse }>({
      type: "TRACK_JOB",
      payload: {
        company: jobInfo.company,
        title: jobInfo.title,
        location: jobInfo.location,
        url: jobInfo.url,
        description: jobInfo.description,
        ats_type: "linkedin",
        difficulty: "auto",
        fit_score: score?.fit_score,
        comp_est: score?.comp_est ?? undefined,
        verdict: score?.verdict,
        gaps: score?.gaps,
      },
    });
    if (result?.type === "TRACK_JOB_RESULT") {
      appId = result.payload.app_id;
    }
  } catch (err) {
    console.warn("[JobCrawler:linkedin] TRACK_JOB failed:", err);
  }

  // 3. Walk the steps.
  const ctx: StepContext = { modal, jobInfo, filledFields: {}, score };
  let stepsCompleted = 0;

  for (let i = 0; i < MAX_STEPS; i++) {
    if (!isModalAttached(modal)) {
      return { success: false, stepsCompleted, error: "modal_closed" };
    }

    let action: ActionType;
    try {
      action = await handleStep(modal, ctx);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[JobCrawler:linkedin] step failed:", err);
      removeOverlay();
      return { success: false, stepsCompleted, error: msg };
    }
    stepsCompleted += 1;

    if (action === "skip") {
      console.log("[JobCrawler:linkedin] user skipped from review panel.");
      removeOverlay();
      return { success: false, stepsCompleted, error: "user_skipped" };
    }

    const btn = findActionButton(modal);
    if (!btn) {
      return { success: false, stepsCompleted, error: "no_action_button" };
    }

    if (action === "submit") {
      // Do NOT auto-click submit yet — leave the final click to the user.
      // Mark the application as ready to submit.
      console.log("[JobCrawler:linkedin] reached Submit — leaving final click to user.");
      if (appId) {
        try {
          await sendMessage<{ type: string }>({
            type: "UPDATE_STATUS",
            payload: {
              app_id: appId,
              status: "applying",
              filled_fields_json: ctx.filledFields,
            },
          });
        } catch (err) {
          console.warn("[JobCrawler:linkedin] UPDATE_STATUS(applying) failed:", err);
        }
      }
      return { success: true, stepsCompleted };
    }

    // Snapshot before clicking Next/Review so we can detect the transition.
    const snapshot = (modal.querySelector("form")?.innerHTML ?? "").slice(0, 2000);
    btn.element.click();
    await waitForStepTransition(modal, snapshot);

    if (!isModalAttached(modal)) {
      // Modal closed after click — could mean submission completed (rare on Next).
      if (appId) {
        try {
          await sendMessage<{ type: string }>({
            type: "UPDATE_STATUS",
            payload: {
              app_id: appId,
              status: "applied",
              filled_fields_json: ctx.filledFields,
            },
          });
        } catch (err) {
          console.warn("[JobCrawler:linkedin] UPDATE_STATUS(applied) failed:", err);
        }
      }
      return { success: true, stepsCompleted };
    }
  }

  return { success: false, stepsCompleted, error: "max_steps_exceeded" };
}

// ── Init (modal observer) ────────────────────────────────────────────────────

const MODAL_SELECTORS = [
  ".jobs-easy-apply-modal",
  'div[role="dialog"][aria-labelledby*="easy-apply"]',
  "div[data-test-modal]",
  '[aria-modal="true"]',
] as const;

function findModal(): Element | null {
  for (const sel of MODAL_SELECTORS) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

function startObserver(): void {
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (!(node instanceof Element)) continue;
        const modal = MODAL_SELECTORS.some((sel) => node.matches(sel))
          ? node
          : node.querySelector(MODAL_SELECTORS.join(", "));
        if (modal) {
          observer.disconnect();
          handleEasyApply(modal)
            .then((result) => {
              console.log("[JobCrawler:linkedin] Apply result:", result);
              // Re-arm so the user can apply to another job in the same tab.
              startObserver();
            })
            .catch((err: unknown) => {
              console.error("[JobCrawler:linkedin] Apply error:", err);
              startObserver();
            });
          return;
        }
      }
    }
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

export function init(): void {
  const existing = findModal();
  if (existing) {
    handleEasyApply(existing)
      .then((result) => {
        console.log("[JobCrawler:linkedin] Apply result:", result);
        startObserver();
      })
      .catch((err: unknown) => {
        console.error("[JobCrawler:linkedin] Apply error:", err);
        startObserver();
      });
    return;
  }
  startObserver();
}
