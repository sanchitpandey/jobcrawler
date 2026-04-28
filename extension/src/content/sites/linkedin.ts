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
  removePanel,
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
  ".jobs-box__html-content",
  ".jobs-description-content__text",
  ".show-more-less-html__markup",
  "#job-details",
  ".jobs-unified-description__content",
  ".jobs-description__container",
  ".jobs-description-content",
  ".jobs-description__text",
  ".jobs-description",
  "[data-test-job-description]",
  "[data-job-description]",
  "section.jobs-description",
  'div[class*="jobs-box__html-content"]',
  'div[class*="jobs-description"] [class*="html-content"]',
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
  batchMode?: boolean;
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
  if (!result || result.type !== "ANSWER_FIELDS_RESULT") {
    const detail =
      (result as { payload?: { message?: string } })?.payload?.message ??
      result?.message ??
      JSON.stringify(result);
    throw new Error(`ANSWER_FIELDS failed: ${detail}`);
  }
  const answers = result.payload?.answers;
  if (!Array.isArray(answers)) {
    console.warn("[JobCrawler:linkedin] ANSWER_FIELDS returned non-array answers:", result);
    return [];
  }
  return answers;
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
  // Give LinkedIn's SDUI state machine time to finish binding question models
  // after the DOM is ready. Mirrors legacy _human_delay(0.8, 1.8) at step start.
  await humanDelay(1000, 1800);

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

    let answers: AnswerItem[];
    if (ctx.batchMode) {
      // Auto-approve non-manual answers; manual_review fields are left unfilled.
      answers = initialAnswers.filter((a) => !a.is_manual_review);
    } else {
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
      removePanel(); // Close review panel; keep score badge.

      if (approved === null) {
        return "skip";
      }

      answers = mergeApprovedAnswers(initialAnswers, approved);
    }
    const results = await fillAllFields(fillable, answers, modal);

    // Audit trail for tracker.
    for (const a of answers) {
      if (a.value && !a.is_manual_review) {
        ctx.filledFields[a.label] = a.value;
      }
    }

    const failed = results.filter((r) => !r.success);
    // manual_review is expected — we intentionally skip those fields.
    const unexpected = failed.filter((r) => r.error !== "manual_review");
    const manualCount = failed.length - unexpected.length;
    if (manualCount > 0) {
      console.log(`[JobCrawler:linkedin] ${manualCount} field(s) left for manual review`);
    }
    if (unexpected.length > 0) {
      console.warn(
        `[JobCrawler:linkedin] ${unexpected.length}/${results.length} fields failed to fill:`,
        JSON.stringify(unexpected),
      );
    }

    // Wait for LinkedIn's React/SDUI state to settle after fill events.
    // 400-800ms is not enough — SDUI async re-renders can take 1-2s.
    await humanDelay(1500, 2500);

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
      await humanDelay(1000, 1500);
    }
  }

  // Wait for any LinkedIn loading spinner to clear before returning the action.
  await waitForLinkedInIdle(modal);

  const action = findActionButton(modal);
  return action?.action ?? "unknown";
}

/**
 * Wait until LinkedIn's loading spinners / skeleton screens inside the modal
 * have cleared. LinkedIn's SDUI async loads questionGroupingViewModels after
 * the DOM skeleton appears; clicking Next before this finishes causes a crash.
 */
async function waitForLinkedInIdle(modal: Element, timeoutMs = 4000): Promise<void> {
  const spinnerSelectors = [
    ".artdeco-spinner",
    "[data-test-spinner]",
    ".jobs-easy-apply-modal__loading",
    ".artdeco-loader",
    '[aria-busy="true"]',
  ];
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const spinning = spinnerSelectors.some((s) => modal.querySelector(s));
    if (!spinning) return;
    await new Promise<void>((r) => setTimeout(r, 200));
  }
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
  filledFields?: Record<string, string>;
}

const MAX_STEPS = 10;

/**
 * Drive the entire Easy Apply flow for `modal`.
 * Pass batchMode=true to skip scoring, tracking, review panel, and status
 * updates — the auto-apply orchestrator handles those externally.
 */
export async function handleEasyApply(modal: Element, batchMode = false): Promise<ApplyResult> {
  const jobInfo = extractJobInfo();
  console.log("[JobCrawler:linkedin] Easy Apply started:", jobInfo, { batchMode });

  let score: ScoreResponse | null = null;
  // appId is null in batch mode — orchestrator owns status updates.
  let appId: string | null = null;

  if (!batchMode) {
    // 1. Score the job (best-effort) and show overlay.
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
      } else {
        const detail = (result as { payload?: { message?: string } })?.payload?.message ?? "unknown";
        console.warn("[JobCrawler:linkedin] SCORE_JOB error:", detail);
      }
    } catch (err) {
      console.warn("[JobCrawler:linkedin] SCORE_JOB failed:", err);
    }

    // 2. Track the job (creates Application row, returns app_id).
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
      } else {
        const detail = (result as { payload?: { message?: string } })?.payload?.message ?? "unknown";
        console.warn("[JobCrawler:linkedin] TRACK_JOB error:", detail);
      }
    } catch (err) {
      console.warn("[JobCrawler:linkedin] TRACK_JOB failed:", err);
    }
  }

  // 3. Walk the steps (shared by interactive and batch modes).
  //    appId is non-null only in interactive mode; `if (appId)` guards skip it in batch.
  const ctx: StepContext = { modal, jobInfo, filledFields: {}, score, batchMode };
  let stepsCompleted = 0;

  for (let i = 0; i < MAX_STEPS; i++) {
    if (!isModalAttached(modal)) {
      return { success: false, stepsCompleted, error: "modal_closed", filledFields: ctx.filledFields };
    }

    let action: ActionType;
    try {
      action = await handleStep(modal, ctx);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error("[JobCrawler:linkedin] step failed:", err);
      removePanel();
      return { success: false, stepsCompleted, error: msg, filledFields: ctx.filledFields };
    }
    stepsCompleted += 1;

    if (action === "skip") {
      console.log("[JobCrawler:linkedin] user skipped from review panel.");
      removeOverlay();
      return { success: false, stepsCompleted, error: "user_skipped", filledFields: ctx.filledFields };
    }

    const btn = findActionButton(modal);
    if (!btn) {
      return { success: false, stepsCompleted, error: "no_action_button", filledFields: ctx.filledFields };
    }

    if (action === "submit") {
      console.log("[JobCrawler:linkedin] Auto-submitting application...");
      if (appId) {
        try {
          await sendMessage<{ type: string }>({
            type: "UPDATE_STATUS",
            payload: { app_id: appId, status: "applying", filled_fields_json: ctx.filledFields },
          });
        } catch (err) {
          console.warn("[JobCrawler:linkedin] UPDATE_STATUS(applying) failed:", err);
        }
      }

      btn.element.click();
      await humanDelay(2000, 3000);

      if (appId && !isModalAttached(modal)) {
        try {
          await sendMessage<{ type: string }>({
            type: "UPDATE_STATUS",
            payload: { app_id: appId, status: "applied", filled_fields_json: ctx.filledFields },
          });
        } catch (err) {
          console.warn("[JobCrawler:linkedin] UPDATE_STATUS(applied) failed:", err);
        }
      }

      return { success: true, stepsCompleted, filledFields: ctx.filledFields };
    }

    // Snapshot before clicking Next/Review so we can detect the transition.
    const snapshot = (modal.querySelector("form")?.innerHTML ?? "").slice(0, 2000);
    btn.element.click();
    await waitForStepTransition(modal, snapshot);

    if (!isModalAttached(modal)) {
      if (appId) {
        try {
          await sendMessage<{ type: string }>({
            type: "UPDATE_STATUS",
            payload: { app_id: appId, status: "applied", filled_fields_json: ctx.filledFields },
          });
        } catch (err) {
          console.warn("[JobCrawler:linkedin] UPDATE_STATUS(applied) failed:", err);
        }
      }
      return { success: true, stepsCompleted, filledFields: ctx.filledFields };
    }
  }

  return { success: false, stepsCompleted, error: "max_steps_exceeded", filledFields: ctx.filledFields };
}

// ── Batch-mode helpers ───────────────────────────────────────────────────────

/**
 * Find the Easy Apply button. LinkedIn's new design uses <a> tags with
 * aria-label="Easy Apply to this job" — aria-label is the most reliable
 * signal since CSS class names are obfuscated.
 */
function findEasyApplyButton(): HTMLElement | null {
  // Priority 1: exact aria-label matches (most reliable in new LinkedIn design)
  const ariaSelectors = [
    "a[aria-label='Easy Apply to this job']",
    "button[aria-label='Easy Apply to this job']",
    "a[aria-label='LinkedIn Apply to this job']",
    "button[aria-label='LinkedIn Apply to this job']",
    "[aria-label*='Easy Apply']",
    "[aria-label*='LinkedIn Apply']",
  ];
  for (const sel of ariaSelectors) {
    const el = document.querySelector<HTMLElement>(sel);
    if (el && !(el as HTMLButtonElement).disabled) return el;
  }

  // Priority 2: class-based selectors scoped to the job top card
  const topCard = document.querySelector(
    ".jobs-unified-top-card, .job-view-layout, .job-details-jobs-unified-top-card"
  );
  if (topCard) {
    for (const sel of [
      "button.jobs-apply-button",
      "a.jobs-apply-button",
      "button[class*='jobs-apply']",
      "a[class*='jobs-apply']",
    ]) {
      const el = topCard.querySelector<HTMLElement>(sel);
      if (!el) continue;
      if ((el as HTMLButtonElement).disabled) continue;
      const text = (el.textContent ?? "").toLowerCase().trim();
      const aria = (el.getAttribute("aria-label") ?? "").toLowerCase();
      if (text.includes("easy apply") || aria.includes("easy apply") ||
          text.includes("linkedin apply") || aria.includes("linkedin apply")) {
        return el;
      }
    }
    // Fallback: any visible button/link in top card with "easy apply" text
    for (const el of Array.from(topCard.querySelectorAll<HTMLElement>("button, a, [role='button']"))) {
      if ((el as HTMLButtonElement).disabled) continue;
      const text = (el.textContent ?? "").toLowerCase().trim();
      const aria = (el.getAttribute("aria-label") ?? "").toLowerCase();
      if (text === "easy apply" || aria === "easy apply to this job" ||
          aria.startsWith("easy apply to ") || aria.startsWith("linkedin apply")) {
        return el;
      }
    }
  }

  // Priority 3: global text scan (last resort)
  for (const el of Array.from(document.querySelectorAll<HTMLElement>("button, a"))) {
    if ((el as HTMLButtonElement).disabled) continue;
    const text = (el.textContent ?? "").toLowerCase().trim();
    const aria = (el.getAttribute("aria-label") ?? "").toLowerCase();
    if (text === "easy apply" || aria.startsWith("easy apply to ") ||
        aria.startsWith("linkedin apply to ")) {
      return el;
    }
  }
  return null;
}

/** Poll until Easy Apply button appears or timeout. */
async function waitForEasyApplyButton(timeoutMs = 20_000): Promise<HTMLElement | null> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const btn = findEasyApplyButton();
    if (btn) return btn;
    await new Promise<void>((r) => setTimeout(r, 400));
  }
  return null;
}

/** Wait for job title — signals that the SPA has rendered job content. */
async function waitForJobTitle(timeoutMs = 12_000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    for (const sel of ["h1.t-24", ".job-details-jobs-unified-top-card__job-title", "h1"]) {
      if (document.querySelector(sel)?.textContent?.trim()) return;
    }
    await new Promise<void>((r) => setTimeout(r, 200));
  }
}

/**
 * Wait for the Easy Apply surface — either:
 *   • Classic: a modal/dialog appears in the same DOM after button click
 *   • SDUI: LinkedIn SPA navigates to /apply/ URL and renders modal in the new route
 *
 * Uses broad selectors matching what LinkedIn actually uses, validated by
 * the presence of form controls or apply-related buttons inside.
 */
async function waitForApplySurface(timeoutMs = 15_000): Promise<Element | null> {
  const specificSelectors = [
    ".jobs-easy-apply-modal",
    ".artdeco-modal",
    '[aria-modal="true"]',
    'div[role="dialog"][aria-labelledby*="easy-apply"]',
    'div[role="dialog"][aria-label*="apply" i]',
  ];

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    // Check specific selectors first
    for (const sel of specificSelectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    // Broader fallback: any dialog that contains form controls or apply buttons
    const anyDialog = document.querySelector('div[role="dialog"]');
    if (anyDialog && anyDialog.querySelector('button, input, select, textarea')) {
      return anyDialog;
    }
    await new Promise<void>((r) => setTimeout(r, 200));
  }
  return null;
}

/** Detect already-applied state scoped to apply button, not page text. */
function isAlreadyApplied(): boolean {
  // Applied indicator on the button itself
  const applyBtn = document.querySelector("button.jobs-apply-button, a.jobs-apply-button");
  if (applyBtn) {
    const text = (applyBtn.textContent ?? "").trim().toLowerCase();
    const aria = (applyBtn.getAttribute("aria-label") ?? "").toLowerCase();
    if (text === "applied" || text === "application submitted") return true;
    if ((aria.includes("applied") || aria.includes("submitted")) &&
        !aria.includes("easy apply")) return true;
  }
  // LinkedIn confirmation banners / disabled applied button
  if (document.querySelector(".jobs-details-top-card__apply-error")) return true;
  const disabledBtn = document.querySelector<HTMLButtonElement>("button.jobs-apply-button[disabled]");
  if (disabledBtn) {
    const t = (disabledBtn.textContent ?? "").trim().toLowerCase();
    if (t === "applied" || t === "application submitted") return true;
  }
  return false;
}

function isCaptchaPresent(): boolean {
  const captchaSelectors = ["#captcha-internal", ".captcha__container", "#challenge", "[data-test-captcha]"];
  if (captchaSelectors.some((s) => document.querySelector(s))) return true;
  const title = document.title.toLowerCase();
  return title.includes("security check") || title.includes("verification");
}

async function runBatchApply(): Promise<void> {
  const report = (msg: { type: "batch_job_complete"; success: boolean; skipped?: boolean; filledFields?: Record<string, string> } | { type: "batch_job_failed"; error: string }): void => {
    chrome.runtime.sendMessage(msg).catch(() => undefined);
  };

  // If we landed on the apply URL directly (SPA re-init or full navigation),
  // skip button-finding and look for the apply surface right away.
  const onApplyUrl = /\/apply\/|openSDUIApplyFlow=true/i.test(window.location.href);

  // Detect session expiry: LinkedIn redirected to login, feed, or home page
  const url = window.location.href;
  const isSessionPage = /linkedin\.com\/(login|checkpoint|uas\/|oauth\/|authwall|feed\/?(\?|#|$))/i.test(url)
    || /^https?:\/\/(www\.)?linkedin\.com\/?(\?|#|$)/i.test(url);
  if (isSessionPage) {
    report({ type: "batch_job_failed", error: "session_expired" });
    return;
  }

  if (!onApplyUrl && !url.match(/linkedin\.com\/jobs\/view\//i)) {
    report({ type: "batch_job_failed", error: "not_job_page" });
    return;
  }

  if (isCaptchaPresent()) {
    report({ type: "batch_job_failed", error: "captcha_detected" });
    return;
  }

  // If already on apply URL, the surface should be visible shortly
  if (onApplyUrl) {
    const surface = await waitForApplySurface(15_000);
    if (!surface) {
      report({ type: "batch_job_failed", error: "apply_surface_not_found" });
      return;
    }
    try {
      const result = await handleEasyApply(surface, true);
      if (result.success) {
        report({ type: "batch_job_complete", success: true, filledFields: result.filledFields ?? {} });
      } else if (result.error === "user_skipped") {
        report({ type: "batch_job_complete", success: false, skipped: true });
      } else {
        report({ type: "batch_job_failed", error: result.error ?? "apply_failed" });
      }
    } catch (e) {
      report({ type: "batch_job_failed", error: String(e) });
    }
    return;
  }

  // Normal job listing page: wait for content, then find and click the button
  await waitForJobTitle();

  if (isAlreadyApplied()) {
    report({ type: "batch_job_complete", success: false, skipped: true });
    return;
  }

  const easyApplyBtn = await waitForEasyApplyButton();
  if (!easyApplyBtn) {
    report({ type: "batch_job_failed", error: "no_easy_apply_button" });
    return;
  }

  // Grab href before clicking — needed if click triggers SPA navigation
  const applyHref = (easyApplyBtn instanceof HTMLAnchorElement)
    ? (easyApplyBtn.getAttribute("href") ?? "")
    : "";

  easyApplyBtn.click();

  // Wait for the apply surface to appear (modal in same DOM, or post-navigation)
  let surface = await waitForApplySurface(12_000);

  // If modal never appeared and we have an href, navigate there directly as fallback
  if (!surface && applyHref) {
    const fullHref = applyHref.startsWith("http")
      ? applyHref
      : `https://www.linkedin.com${applyHref}`;
    window.location.href = fullHref;
    // After navigation, the new content script will pick up batchMode and retry
    return;
  }

  if (!surface) {
    report({ type: "batch_job_failed", error: "modal_not_found" });
    return;
  }

  try {
    const result = await handleEasyApply(surface, true);
    if (result.success) {
      report({ type: "batch_job_complete", success: true, filledFields: result.filledFields ?? {} });
    } else if (result.error === "user_skipped") {
      report({ type: "batch_job_complete", success: false, skipped: true });
    } else {
      report({ type: "batch_job_failed", error: result.error ?? "apply_failed" });
    }
  } catch (e) {
    const errMsg = String(e);
    if (errMsg.toLowerCase().includes("captcha")) {
      report({ type: "batch_job_failed", error: "captcha_detected" });
    } else {
      report({ type: "batch_job_failed", error: errMsg });
    }
  }
}

// ── Init (modal observer) ────────────────────────────────────────────────────

const MODAL_SELECTORS = [
  ".jobs-easy-apply-modal",
  ".artdeco-modal",
  '[aria-modal="true"]',
  'div[role="dialog"][aria-labelledby*="easy-apply"]',
  'div[role="dialog"][aria-label*="apply" i]',
  "div[data-test-modal]",
] as const;

function findModal(): Element | null {
  for (const sel of MODAL_SELECTORS) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  // Last-resort: any dialog with form controls
  const anyDialog = document.querySelector('div[role="dialog"]');
  if (anyDialog && anyDialog.querySelector('button, input, select')) return anyDialog;
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

/**
 * Score the current job on page load (best-effort).
 * Shows a floating badge without opening the Easy Apply modal.
 */
async function scoreOnPageLoad(): Promise<void> {
  const jobInfo = extractJobInfo();
  if (!jobInfo.title && !jobInfo.description) return; // Not on a job detail page.

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
    if (result?.type === "SCORE_JOB_RESULT" && result.payload) {
      showScoreBadge(result.payload);
    } else {
      const detail = (result as { payload?: { message?: string } })?.payload?.message ?? "unknown";
      console.warn("[JobCrawler:linkedin] page score error:", detail);
    }
  } catch (err) {
    console.warn("[JobCrawler:linkedin] page score failed:", err);
  }
}

/**
 * LinkedIn is a SPA — navigating between jobs changes the URL without a full
 * page reload, so the content script only runs once.  We watch for URL changes
 * and re-score whenever the user lands on a new job detail page.
 *
 * We debounce by 1.5 s to give LinkedIn's React time to render the job title
 * and description into the DOM before we try to extract them.
 */
function watchJobNavigation(): void {
  let lastUrl = window.location.href;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  const triggerScore = (): void => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      scoreOnPageLoad().catch(() => undefined);
    }, 1500);
  };

  // Intercept history.pushState (LinkedIn's primary SPA navigation method).
  const origPushState = history.pushState.bind(history);
  history.pushState = function (...args: Parameters<typeof history.pushState>) {
    origPushState(...args);
    triggerScore();
  };

  // popstate covers back/forward navigation.
  window.addEventListener("popstate", triggerScore);

  // MutationObserver as a belt-and-suspenders fallback for any other DOM-driven
  // navigation that doesn't go through history.pushState.
  const navObserver = new MutationObserver(() => {
    const current = window.location.href;
    if (current !== lastUrl) {
      lastUrl = current;
      if (current.includes("/jobs/")) triggerScore();
    }
  });
  navObserver.observe(document.body, { childList: true, subtree: false });
}

export async function init(): Promise<void> {
  const { batchMode } = (await chrome.storage.local.get("batchMode")) as { batchMode?: boolean };

  if (batchMode) {
    // Batch mode: orchestrator opened this tab; run apply flow and signal completion.
    await runBatchApply();
    return;
  }

  // Interactive mode (existing flow).
  scoreOnPageLoad().catch(() => undefined);
  watchJobNavigation();

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
