/**
 * linkedin.ts — LinkedIn Easy Apply handler
 *
 * Watches for the Easy Apply modal, scans its fields, asks the service worker
 * to fill them via ANSWER_FIELDS, fills each element with React-safe DOM events,
 * and re-runs on every modal step when the user clicks Next.
 * Never touches the Submit button.
 */

import { scanFields } from "../field-scanner.js";
import { showOverlay } from "../../overlay/overlay.js";
import { fillAllFields } from "../form-filler.js";
import type {
  AnswerItem,
  Message,
  ScoreResponse,
} from "../../types/index.js";

// ── Selectors ─────────────────────────────────────────────────────────────────

const MODAL_SELECTORS = [
  "div[data-test-modal]",
  "div.jobs-easy-apply-modal",
] as const;

const JOB_DESC_SELECTORS = [
  ".jobs-description__content",
  ".jobs-description-content__text",
  ".jobs-description",
  "[data-test-job-description]",
] as const;

// Buttons whose click must NOT trigger a fill-on-next-step cycle.
const SUBMIT_LABELS = ["submit application", "submit"];

// ── Helpers ───────────────────────────────────────────────────────────────────

function scrapeJobDescription(): string {
  for (const sel of JOB_DESC_SELECTORS) {
    const el = document.querySelector(sel);
    if (el) return (el.textContent ?? "").trim();
  }
  return "";
}

/** Promisified chrome.runtime.sendMessage. */
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

// ── Step handler ──────────────────────────────────────────────────────────────

async function handleStep(modal: Element) {
  console.log("[JobCrawler:linkedin] Scanning fields in modal...");
  const fields = scanFields(modal);
  console.log(`[JobCrawler:linkedin] Found ${fields.length} fields:`, fields);
  
  if (fields.length === 0) {
      console.log("[JobCrawler:linkedin] No fields detected, skipping this step.");
      return;
  }

  const title = document.querySelector(
    "h1.t-24, h1.jobs-unified-top-card__job-title"
  )?.textContent?.trim() ?? "";
  const company = document.querySelector(
    ".jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name"
  )?.textContent?.trim() ?? "";

  let result;
  try {
    console.log("[JobCrawler:linkedin] Sending ANSWER_FIELDS to background script...");
    result = await sendMessage<any>({
      type: "ANSWER_FIELDS",
      payload: { fields, company, jobTitle: title },
    });
    console.log("[JobCrawler:linkedin] Received response from background script:", result);
  } catch (err: unknown) {
    console.error("[JobCrawler:linkedin] ANSWER_FIELDS failed:", err);
    return;
  }

  if (result?.type !== "ANSWER_FIELDS_RESULT") {
      console.log("[JobCrawler:linkedin] Background response was not a success result:", result);
      return;
  }

  const answers: AnswerItem[] = result.payload.answers ?? [];
  console.log("[JobCrawler:linkedin] Using answers from backend:", answers);

  const fillResults = await fillAllFields(fields, answers, modal);
  const failed = fillResults.filter((r) => !r.success);
  if (failed.length) {
    console.warn(
      `[JobCrawler:linkedin] ${failed.length}/${fillResults.length} fields not filled:`,
      failed
    );
  }
}

// ── Score the current listing and surface the overlay ─────────────────────────

async function scoreListing(): Promise<void> {
  const title =
    document.querySelector<HTMLElement>(
      "h1.t-24, h1.jobs-unified-top-card__job-title"
    )?.textContent?.trim() ?? "";
  const company =
    document.querySelector<HTMLElement>(
      ".jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name"
    )?.textContent?.trim() ?? "";
  const description = scrapeJobDescription();

  if (!title && !description) return; // not enough data

  type ScoreResult = { type: "SCORE_JOB_RESULT"; payload: ScoreResponse };
  try {
    const result = await sendMessage<ScoreResult>({
      type: "SCORE_JOB",
      payload: { title, company, description, url: window.location.href },
    });
    if (result?.type === "SCORE_JOB_RESULT") {
      showOverlay(result.payload);
    }
  } catch (err) {
    console.warn("[JobCrawler:linkedin] SCORE_JOB failed:", err);
  }
}

// ── Modal lifecycle ───────────────────────────────────────────────────────────

function handleModalFound(modal: Element): void {
  console.log("[JobCrawler:linkedin] Easy Apply modal detected");

  // Fill the first step immediately
  handleStep(modal).catch((err: unknown) =>
    console.error("[JobCrawler:linkedin] initial step fill failed:", err)
  );

  // Score and display the overlay (fire-and-forget)
  scoreListing().catch(() => undefined);

  // Delegate click listener — re-fill on Next/Continue/Review clicks.
  // Never re-fill on Submit.
  modal.addEventListener("click", (e: Event) => {
    const btn = (e.target as Element).closest<HTMLButtonElement>("button");
    if (!btn) return;

    const btnLabel = (
      btn.getAttribute("aria-label") ??
      btn.textContent ??
      ""
    )
      .trim()
      .toLowerCase();

    if (SUBMIT_LABELS.some((s) => btnLabel.includes(s))) return;

    if (
      ["next", "continue", "review"].some((kw) => btnLabel.includes(kw))
    ) {
      // LinkedIn animates the step transition — wait for new DOM
      setTimeout(() => {
        handleStep(modal).catch((err: unknown) =>
          console.error("[JobCrawler:linkedin] step fill failed:", err)
        );
      }, 400);
    }
  });
}

function findModal(): Element | null {
  for (const sel of MODAL_SELECTORS) {
    const el = document.querySelector(sel);
    if (el) return el;
  }
  return null;
}

// ── Entry point ───────────────────────────────────────────────────────────────

export function init(): void {
  // Handle modal if it's already present on init
  const existing = findModal();
  if (existing) {
    handleModalFound(existing);
    return;
  }

  // Watch document.body for the modal being injected into the DOM
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      for (const node of mutation.addedNodes) {
        if (!(node instanceof Element)) continue;
        // Match the added node itself, or a descendant
        const modal =
          MODAL_SELECTORS.find((sel) => node.matches(sel))
            ? node
            : node.querySelector(
                MODAL_SELECTORS.join(", ")
              );
        if (modal) {
          observer.disconnect(); // one-shot; re-arm after modal closes if needed
          handleModalFound(modal);
          return;
        }
      }
    }
  });

  observer.observe(document.body, { childList: true, subtree: true });
}
