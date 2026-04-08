/**
 * overlay.ts
 *
 * Shadow-DOM-isolated UI for the extension. Provides:
 *   - showScoreBadge():   floating pill with the job fit score
 *   - showReviewPanel():  right-side review panel — user inspects/edits answers
 *                         before the form is filled
 *   - removeOverlay():    cleanup
 *
 * Uses Shadow DOM so LinkedIn's CSS (Artdeco / BEM) cannot bleed into
 * our markup and our styles cannot bleed into theirs.
 */

import type { ApiField, AnswerItem, ScoreResponse } from "../types/index.js";

// ── Public types ─────────────────────────────────────────────────────────────

export interface ApprovedAnswer {
  label: string;
  value: string;     // possibly edited by the user
  approved: boolean; // false → field should be skipped
}

export interface JobInfoLite {
  title: string;
  company: string;
  location: string;
  score?: number;
  verdict?: string;
}

// ── Constants ────────────────────────────────────────────────────────────────

const HOST_ID = "jobcrawler-overlay-host";
const BADGE_HOST_ID = "jobcrawler-badge-host";

// Module-level handle to the most recently created shadow root.
// Exposed via __getShadowRoot() for testing only.
let _activeShadow: ShadowRoot | null = null;

// ── HTML escape ──────────────────────────────────────────────────────────────

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ── Stylesheet injected into every shadow root ───────────────────────────────

const OVERLAY_CSS = `
:host, * { box-sizing: border-box; }

.jc-root {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  font-size: 14px;
  color: #0f172a;
  -webkit-font-smoothing: antialiased;
}

/* ── Score badge ─────────────────────────────────────────────────────────── */

.jc-badge {
  position: fixed;
  top: 16px;
  right: 16px;
  background: #ffffff;
  border-radius: 999px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.15);
  padding: 8px 14px 8px 8px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
  border: 1px solid #e2e8f0;
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.jc-badge:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(15,23,42,0.18); }

.jc-badge-circle {
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 14px; color: #fff;
}
.jc-badge-circle--good   { background: #22c55e; }
.jc-badge-circle--ok     { background: #f59e0b; }
.jc-badge-circle--poor   { background: #ef4444; }

.jc-badge-text { font-weight: 600; font-size: 13px; }

.jc-badge-detail {
  display: none;
  position: absolute; top: 100%; right: 0; margin-top: 8px;
  background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 14px; min-width: 240px; max-width: 320px;
  box-shadow: 0 8px 24px rgba(15,23,42,0.15);
  font-size: 13px; line-height: 1.45;
}
.jc-badge.jc-badge--expanded .jc-badge-detail { display: block; }
.jc-badge-detail h4 {
  margin: 0 0 6px 0; font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.05em; color: #64748b;
}
.jc-badge-detail ul { margin: 0 0 8px 0; padding-left: 16px; }
.jc-badge-detail li { margin-bottom: 3px; color: #334155; }
.jc-badge-comp { color: #475569; font-size: 12px; }

/* ── Review panel ────────────────────────────────────────────────────────── */

.jc-backdrop {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.35);
  animation: jc-fade 150ms ease;
}
@keyframes jc-fade { from { opacity: 0; } to { opacity: 1; } }

.jc-panel {
  position: fixed; top: 0; right: 0; height: 100vh;
  width: 420px; max-width: 100vw;
  background: #ffffff;
  display: flex; flex-direction: column;
  box-shadow: -4px 0 24px rgba(15, 23, 42, 0.18);
  animation: jc-slide 220ms cubic-bezier(0.2, 0.9, 0.3, 1);
}
@keyframes jc-slide {
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
}

.jc-header {
  padding: 18px 20px 14px 20px;
  border-bottom: 1px solid #e2e8f0;
}
.jc-header-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px;
}
.jc-title { font-size: 13px; font-weight: 700; color: #0f172a; letter-spacing: 0.02em; }
.jc-score-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 700; color: #fff;
}
.jc-score-pill--good { background: #22c55e; }
.jc-score-pill--ok   { background: #f59e0b; }
.jc-score-pill--poor { background: #ef4444; }
.jc-job { font-size: 13px; color: #475569; }

.jc-field-list {
  flex: 1 1 auto; overflow-y: auto;
  padding: 16px 20px;
}
.jc-field {
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #ffffff;
}
.jc-field--review {
  background: #fffbeb;
  border-color: #fcd34d;
}
.jc-field-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 10px;
}
.jc-field-label {
  font-size: 13px; font-weight: 600; color: #0f172a;
  flex: 1 1 auto;
}
.jc-confidence {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 600;
  padding: 3px 8px; border-radius: 999px;
  white-space: nowrap;
}
.jc-confidence::before {
  content: ""; width: 6px; height: 6px; border-radius: 50%;
}
.jc-confidence--pattern { background: #ecfdf5; color: #047857; }
.jc-confidence--pattern::before { background: #22c55e; }
.jc-confidence--ai      { background: #eff6ff; color: #1d4ed8; }
.jc-confidence--ai::before { background: #2563eb; }
.jc-confidence--review  { background: #fef3c7; color: #92400e; }
.jc-confidence--review::before { background: #f59e0b; }

.jc-field-value {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
  font-family: inherit;
  color: #0f172a;
  background: #ffffff;
  resize: vertical;
}
.jc-field-value:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15);
}
textarea.jc-field-value { min-height: 70px; }

.jc-footer {
  border-top: 1px solid #e2e8f0;
  padding: 14px 20px 18px 20px;
  background: #ffffff;
}
.jc-summary {
  font-size: 12px; color: #64748b; margin-bottom: 12px;
}
.jc-actions {
  display: flex; gap: 10px;
}
.jc-btn {
  flex: 1;
  padding: 10px 14px;
  font-size: 13px; font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  border: 1px solid transparent;
  transition: background 120ms ease, border-color 120ms ease;
}
.jc-btn-skip {
  background: #ffffff; color: #475569; border-color: #cbd5e1;
}
.jc-btn-skip:hover { background: #f1f5f9; }
.jc-btn-submit {
  background: #2563eb; color: #ffffff;
}
.jc-btn-submit:hover { background: #1d4ed8; }
`;

// ── Shadow host helpers ──────────────────────────────────────────────────────

/**
 * Create and inject a fresh overlay host element with an isolated Shadow DOM.
 * Returns the shadow root so callers can render content into it.
 */
function createOverlayHost(id: string = HOST_ID): ShadowRoot {
  // Remove any pre-existing host with the same id (idempotent).
  document.getElementById(id)?.remove();

  const host = document.createElement("div");
  host.id = id;
  // `all: initial` resets host-page CSS inheritance into our host node.
  host.style.cssText =
    "all: initial; position: fixed; top: 0; right: 0; z-index: 2147483647;";
  document.body.appendChild(host);

  // `open` mode lets tests inspect the shadow root via host.shadowRoot.
  // Closed mode adds zero security in a content-script context (page scripts
  // can monkey-patch attachShadow), so we trade it for testability.
  const shadow = host.attachShadow({ mode: "open" });

  const style = document.createElement("style");
  style.textContent = OVERLAY_CSS;
  shadow.appendChild(style);

  const root = document.createElement("div");
  root.className = "jc-root";
  shadow.appendChild(root);

  _activeShadow = shadow;
  return shadow;
}

// ── Score badge ──────────────────────────────────────────────────────────────

function badgeBucket(score: number): "good" | "ok" | "poor" {
  if (score >= 70) return "good";
  if (score >= 50) return "ok";
  return "poor";
}

function verdictText(verdict: string | undefined, score: number): string {
  const v = (verdict ?? "").toLowerCase();
  if (v.includes("strong")) return "Strong";
  if (v === "yes" || v.includes("good")) return "Good";
  if (v.includes("maybe")) return "Maybe";
  if (v === "no" || v.includes("poor")) return "Poor";
  // Fallback by score band.
  const bucket = badgeBucket(score);
  return bucket === "good" ? "Good" : bucket === "ok" ? "Maybe" : "Poor";
}

/**
 * Show a floating score badge on the job listing page.
 * Click to expand and view gaps + comp estimate.
 */
export function showScoreBadge(score: ScoreResponse): void {
  const shadow = createOverlayHost(BADGE_HOST_ID);
  const root = shadow.querySelector(".jc-root") as HTMLElement;

  const bucket = badgeBucket(score.fit_score);
  const verdict = verdictText(score.verdict, score.fit_score);

  const gapsHtml = (score.gaps ?? []).length
    ? `<h4>Gaps</h4><ul>${score.gaps
        .map((g) => `<li>${escapeHtml(g)}</li>`)
        .join("")}</ul>`
    : "";

  const compHtml = score.comp_est
    ? `<div class="jc-badge-comp">${escapeHtml(score.comp_est)}</div>`
    : "";

  root.innerHTML = `
    <div class="jc-badge" data-bucket="${bucket}">
      <div class="jc-badge-circle jc-badge-circle--${bucket}">${score.fit_score}</div>
      <div class="jc-badge-text">${escapeHtml(verdict)}</div>
      <div class="jc-badge-detail">
        ${gapsHtml}
        ${compHtml}
      </div>
    </div>
  `;

  const badge = root.querySelector<HTMLElement>(".jc-badge")!;
  badge.addEventListener("click", () => {
    badge.classList.toggle("jc-badge--expanded");
  });
}

// ── Review panel ─────────────────────────────────────────────────────────────

interface ConfidenceMeta {
  cls: "pattern" | "ai" | "review";
  text: string;
}

function confidenceMeta(answer: AnswerItem): ConfidenceMeta {
  if (answer.is_manual_review) return { cls: "review", text: "review" };
  if (answer.source === "pattern" || answer.source === "cache") {
    return { cls: "pattern", text: answer.source };
  }
  if (answer.source === "llm") {
    const pct = Math.round((answer.confidence || 0) * 100);
    return { cls: "ai", text: `AI ${pct}%` };
  }
  return { cls: "review", text: "review" };
}

function renderField(
  field: ApiField,
  answer: AnswerItem | undefined,
  index: number,
): string {
  const value = answer?.value ?? "";
  const meta: ConfidenceMeta = answer
    ? confidenceMeta(answer)
    : { cls: "review", text: "review" };
  const isReview = meta.cls === "review";
  const isLong = (value?.length ?? 0) > 60 || field.type === "textarea";

  const inputHtml = isLong
    ? `<textarea class="jc-field-value" data-idx="${index}" placeholder="Write your answer...">${escapeHtml(
        value,
      )}</textarea>`
    : `<input class="jc-field-value" data-idx="${index}" type="text" value="${escapeHtml(
        value,
      )}" placeholder="Write your answer..." />`;

  return `
    <div class="jc-field${isReview ? " jc-field--review" : ""}">
      <div class="jc-field-header">
        <div class="jc-field-label">${escapeHtml(field.label || field.name)}</div>
        <div class="jc-confidence jc-confidence--${meta.cls}">${escapeHtml(meta.text)}</div>
      </div>
      ${inputHtml}
    </div>
  `;
}

function buildSummary(answers: AnswerItem[]): string {
  let pattern = 0;
  let ai = 0;
  let review = 0;
  for (const a of answers) {
    if (a.is_manual_review) review++;
    else if (a.source === "llm") ai++;
    else pattern++;
  }
  const parts: string[] = [];
  parts.push(`${pattern} auto-filled`);
  if (ai) parts.push(`${ai} AI-generated`);
  if (review) parts.push(`${review} needs review`);
  return parts.join(" · ");
}

/**
 * Show the review panel and wait for user action.
 * Resolves with the (possibly edited) approved answers, or null if skipped.
 */
export function showReviewPanel(
  jobInfo: JobInfoLite,
  fields: ApiField[],
  answers: AnswerItem[],
): Promise<ApprovedAnswer[] | null> {
  return new Promise((resolve) => {
    const shadow = createOverlayHost(HOST_ID);
    const root = shadow.querySelector(".jc-root") as HTMLElement;

    // Pair fields with answers by label (answers may be in different order).
    const answerByLabel = new Map<string, AnswerItem>();
    for (const a of answers) answerByLabel.set(a.label, a);

    const score = jobInfo.score;
    const scoreBucket =
      score === undefined ? null : badgeBucket(score);
    const scorePillHtml =
      score !== undefined && scoreBucket
        ? `<span class="jc-score-pill jc-score-pill--${scoreBucket}">${score} ${escapeHtml(
            verdictText(jobInfo.verdict, score),
          )}</span>`
        : "";

    const fieldsHtml = fields
      .map((f, i) => renderField(f, answerByLabel.get(f.label), i))
      .join("");

    const summary = buildSummary(answers);

    const jobLine = [jobInfo.company, jobInfo.title, jobInfo.location]
      .filter(Boolean)
      .map(escapeHtml)
      .join(" — ");

    root.innerHTML = `
      <div class="jc-backdrop" data-jc="backdrop"></div>
      <div class="jc-panel" role="dialog" aria-label="JobCrawler review">
        <div class="jc-header">
          <div class="jc-header-row">
            <div class="jc-title">JOBCRAWLER REVIEW</div>
            ${scorePillHtml}
          </div>
          <div class="jc-job">${jobLine}</div>
        </div>
        <div class="jc-field-list">
          ${fieldsHtml || '<div style="color:#64748b;font-size:13px;">No fields to review.</div>'}
        </div>
        <div class="jc-footer">
          <div class="jc-summary">${escapeHtml(summary)}</div>
          <div class="jc-actions">
            <button class="jc-btn jc-btn-skip" data-jc="skip">Skip Job</button>
            <button class="jc-btn jc-btn-submit" data-jc="submit">Submit Application →</button>
          </div>
        </div>
      </div>
    `;

    let settled = false;

    const collectAnswers = (): ApprovedAnswer[] => {
      const inputs = Array.from(
        root.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>(
          ".jc-field-value",
        ),
      );
      const out: ApprovedAnswer[] = [];
      for (const input of inputs) {
        const idx = Number(input.dataset.idx);
        const field = fields[idx];
        if (!field) continue;
        out.push({
          label: field.label,
          value: input.value,
          approved: true,
        });
      }
      return out;
    };

    const settle = (result: ApprovedAnswer[] | null): void => {
      if (settled) return;
      settled = true;
      window.removeEventListener("keydown", onKeydown, true);
      resolve(result);
    };

    const onKeydown = (e: KeyboardEvent): void => {
      if (e.key === "Escape") {
        e.preventDefault();
        settle(null);
        return;
      }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        settle(collectAnswers());
      }
    };
    window.addEventListener("keydown", onKeydown, true);

    root
      .querySelector<HTMLButtonElement>('[data-jc="skip"]')!
      .addEventListener("click", () => settle(null));
    root
      .querySelector<HTMLButtonElement>('[data-jc="submit"]')!
      .addEventListener("click", () => settle(collectAnswers()));
    root
      .querySelector<HTMLElement>('[data-jc="backdrop"]')!
      .addEventListener("click", () => settle(null));
  });
}

// ── Cleanup ──────────────────────────────────────────────────────────────────

/** Remove all overlay elements (panel + badge) from the page. */
export function removeOverlay(): void {
  document.getElementById(HOST_ID)?.remove();
  document.getElementById(BADGE_HOST_ID)?.remove();
  _activeShadow = null;
}

// ── Backwards compatibility ──────────────────────────────────────────────────

/** @deprecated Use showScoreBadge instead. Retained for callers not yet migrated. */
export function showOverlay(score: ScoreResponse): void {
  showScoreBadge(score);
}

/** @deprecated Use removeOverlay instead. */
export function hideOverlay(): void {
  removeOverlay();
}

// ── Test-only hooks ──────────────────────────────────────────────────────────

/** @internal — used by tests to inspect the most recent shadow root. */
export function __getActiveShadowRoot(): ShadowRoot | null {
  return _activeShadow;
}
