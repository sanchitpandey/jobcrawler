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
.jc-root, .jc-root * { pointer-events: auto; }

.jc-root {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", sans-serif;
  font-size: 14px;
  -webkit-font-smoothing: antialiased;
}

/* ── Score badge ─────────────────────────────────────────────────────────── */

.jc-badge {
  position: fixed;
  top: 72px;
  right: 16px;
  background: #0B0B0F;
  border: 1px solid #2A2A33;
  border-radius: 999px;
  padding: 6px 14px 6px 6px;
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  user-select: none;
  box-shadow: 0 8px 32px rgba(0,0,0,.5), 0 0 0 1px rgba(255,138,31,.15);
  transition: transform 120ms ease, box-shadow 120ms ease;
}
.jc-badge:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 36px rgba(0,0,0,.6), 0 0 0 1px rgba(255,138,31,.25);
}

.jc-badge-circle {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 12px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
}
.jc-badge-circle--good { background: #7DDC8A; color: #0B0B0F; }
.jc-badge-circle--ok   { background: #FF8A1F; color: #0B0B0F; }
.jc-badge-circle--poor { background: #FF6A6A; color: #0B0B0F; }

.jc-badge-text {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 11px; color: #EDE6D6;
}

.jc-badge-tag {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 9px; color: #6B6A63;
  text-transform: uppercase; letter-spacing: .08em;
  border-left: 1px solid #2A2A33; padding-left: 10px;
}

.jc-badge-detail {
  display: none;
  position: absolute; top: 100%; right: 0; margin-top: 8px;
  background: #111116; border: 1px solid #1F1F26; border-radius: 12px;
  padding: 14px 16px; min-width: 240px; max-width: 320px;
  box-shadow: 0 12px 32px rgba(0,0,0,.6);
  font-size: 13px; line-height: 1.5; color: #EDE6D6;
}
.jc-badge.jc-badge--expanded .jc-badge-detail { display: block; }
.jc-badge-detail h4 {
  margin: 0 0 8px 0; font-size: 10px; font-weight: 600;
  text-transform: uppercase; letter-spacing: .08em; color: #6B6A63;
  font-family: "JetBrains Mono", monospace;
}
.jc-badge-detail ul { margin: 0 0 10px 0; padding-left: 16px; }
.jc-badge-detail li { margin-bottom: 4px; color: #A8A192; font-size: 12px; }
.jc-badge-comp { color: #A8A192; font-size: 12px; font-family: "JetBrains Mono", monospace; }

/* ── Review panel ────────────────────────────────────────────────────────── */

.jc-backdrop {
  position: fixed; inset: 0;
  background: rgba(11, 11, 15, 0.6);
  animation: jc-fade 150ms ease;
}
@keyframes jc-fade { from { opacity: 0; } to { opacity: 1; } }

.jc-panel {
  position: fixed; top: 0; right: 0; height: 100vh;
  width: 420px; max-width: 100vw;
  background: #0B0B0F;
  border-left: 1px solid #1F1F26;
  display: flex; flex-direction: column;
  box-shadow: -8px 0 40px rgba(0,0,0,.6);
  animation: jc-slide 220ms cubic-bezier(0.2, 0.9, 0.3, 1);
}
@keyframes jc-slide {
  from { transform: translateX(100%); }
  to   { transform: translateX(0); }
}

.jc-header {
  padding: 20px;
  border-bottom: 1px solid #1F1F26;
}
.jc-header-row {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
}
.jc-title {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px; color: #6B6A63;
  text-transform: uppercase; letter-spacing: .1em;
}
.jc-close-btn {
  background: none; border: none; cursor: pointer;
  color: #6B6A63; font-size: 16px; line-height: 1; padding: 0;
  transition: color .1s;
}
.jc-close-btn:hover { color: #EDE6D6; }

.jc-score-row {
  display: flex; align-items: center; gap: 14px;
}
.jc-score-big {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 44px; line-height: 1; font-variant-numeric: tabular-nums;
}
.jc-score-big--good { color: #FF8A1F; }
.jc-score-big--ok   { color: #FF8A1F; }
.jc-score-big--poor { color: #FF6A6A; }

.jc-score-pill {
  display: inline-flex; align-items: center;
  padding: 2px 8px; border-radius: 999px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 9px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
  margin-bottom: 4px;
}
.jc-score-pill--good { background: rgba(125,220,138,0.15); color: #7DDC8A; }
.jc-score-pill--ok   { background: rgba(255,138,31,0.15);  color: #FFB061; }
.jc-score-pill--poor { background: rgba(255,106,106,0.15); color: #FF6A6A; }

.jc-job-title { font-size: 14px; font-weight: 500; color: #EDE6D6; line-height: 1.3; }
.jc-job-meta  { font-family: "JetBrains Mono", monospace; font-size: 11px; color: #A8A192; margin-top: 2px; }

.jc-field-list {
  flex: 1 1 auto; overflow-y: auto;
  padding: 20px;
  scrollbar-width: thin; scrollbar-color: #2A2A33 transparent;
}
.jc-fields-label {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 9px; color: #6B6A63;
  text-transform: uppercase; letter-spacing: .1em;
  margin-bottom: 12px;
}
.jc-field {
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid #1F1F26;
  border-radius: 8px;
  background: #111116;
}
.jc-field--review {
  border-color: rgba(255,138,31,0.5);
  background: rgba(255,138,31,0.04);
}
.jc-field-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 10px;
}
.jc-field-label {
  font-size: 11px; font-weight: 500; color: #EDE6D6;
  flex: 1 1 auto;
}
.jc-confidence {
  display: inline-flex; align-items: center;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 8.5px; font-weight: 600;
  padding: 2px 7px; border-radius: 999px;
  text-transform: uppercase; letter-spacing: .06em;
  white-space: nowrap;
}
.jc-confidence--pattern { background: rgba(125,220,138,0.12); color: #7DDC8A; }
.jc-confidence--ai      { background: rgba(255,138,31,0.12);  color: #FF8A1F; }
.jc-confidence--review  { background: rgba(255,138,31,0.2);   color: #FFB061; }

.jc-field-value {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid #2A2A33;
  border-radius: 6px;
  font-size: 12px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  color: #EDE6D6;
  background: #0B0B0F;
  resize: vertical;
  transition: border-color .12s;
}
.jc-field-value:focus {
  outline: none;
  border-color: #FF8A1F;
}
textarea.jc-field-value { min-height: 70px; }

.jc-footer {
  border-top: 1px solid #1F1F26;
  padding: 14px 20px 18px 20px;
  background: rgba(17,17,22,0.5);
}
.jc-summary {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 10px; color: #A8A192; margin-bottom: 12px;
}
.jc-shortcut {
  text-align: center;
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 9px; color: #6B6A63; margin-top: 8px;
}
.jc-actions {
  display: flex; gap: 10px;
}
.jc-btn {
  flex: 1;
  padding: 10px 14px;
  font-size: 12px; font-weight: 600;
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  border: 1px solid transparent;
  transition: background 120ms ease, border-color 120ms ease;
}
.jc-btn-skip {
  background: #0B0B0F; color: #EDE6D6; border-color: #1F1F26;
}
.jc-btn-skip:hover { background: #1F1F26; }
.jc-btn-submit {
  background: #FF8A1F; color: #0B0B0F;
}
.jc-btn-submit:hover { background: #FFB061; }
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

  // The review panel host must cover the full viewport so hit-testing works
  // for both the full-screen backdrop and the 420px panel. The badge host
  // only needs to sit in the top-right corner.
  const isPanel = id === HOST_ID;
  host.style.cssText = isPanel
    ? "all: initial; position: fixed; inset: 0; z-index: 2147483647; pointer-events: none;"
    : "all: initial; position: fixed; top: 0; right: 0; z-index: 2147483647;";

  // LinkedIn's Easy Apply modal implements a focus trap: it listens for
  // mousedown/click at the document level and refocuses the modal whenever a
  // click lands on an element outside it.  Our shadow host IS outside the
  // modal in the light DOM, so LinkedIn would intercept every click before our
  // shadow-DOM inputs can receive focus.  Stopping propagation at the host
  // boundary lets our inputs work while keeping LinkedIn's handlers in the dark.
  for (const type of ["mousedown", "click", "keydown"] as const) {
    host.addEventListener(type, (e) => e.stopPropagation(), false);
  }

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
      <div class="jc-badge-text">${escapeHtml(verdict)} match</div>
      <div class="jc-badge-tag">jc</div>
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
    // Defensive: coerce to array in case the API response was malformed.
    const safeAnswers: AnswerItem[] = Array.isArray(answers) ? answers : [];
    const answerByLabel = new Map<string, AnswerItem>();
    for (const a of safeAnswers) answerByLabel.set(a.label, a);

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

    const summary = buildSummary(safeAnswers);

    const jobLine = [jobInfo.company, jobInfo.title, jobInfo.location]
      .filter(Boolean)
      .map(escapeHtml)
      .join(" — ");

    const scoreNum = score !== undefined ? String(score) : "";
    const scoreRowHtml = score !== undefined && scoreBucket ? `
      <div class="jc-score-row">
        <div class="jc-score-big jc-score-big--${scoreBucket}">${scoreNum}</div>
        <div>
          ${scorePillHtml}
          <div class="jc-job-title">${escapeHtml(jobInfo.title)}</div>
          <div class="jc-job-meta">${[jobInfo.company, jobInfo.location].filter(Boolean).map(escapeHtml).join(" · ")}</div>
        </div>
      </div>
    ` : `<div class="jc-job-title">${jobLine}</div>`;

    root.innerHTML = `
      <div class="jc-backdrop" data-jc="backdrop"></div>
      <div class="jc-panel" role="dialog" aria-label="JobCrawler review">
        <div class="jc-header">
          <div class="jc-header-row">
            <div class="jc-title">jobcrawler · review</div>
            <button class="jc-close-btn" data-jc="close" aria-label="Close">×</button>
          </div>
          ${scoreRowHtml}
        </div>
        <div class="jc-field-list">
          <div class="jc-fields-label">Form fields · ${fields.length} detected</div>
          ${fieldsHtml || '<div style="color:#6B6A63;font-size:12px;font-family:monospace;">No fields to review.</div>'}
        </div>
        <div class="jc-footer">
          <div class="jc-summary">${escapeHtml(summary)}</div>
          <div class="jc-actions">
            <button class="jc-btn jc-btn-skip" data-jc="skip">Skip job</button>
            <button class="jc-btn jc-btn-submit" data-jc="submit">Submit application →</button>
          </div>
          <div class="jc-shortcut">⌘ + ↵ to submit · esc to cancel</div>
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

    for (const el of root.querySelectorAll<HTMLElement>('[data-jc="skip"], [data-jc="close"]')) {
      el.addEventListener("click", () => settle(null));
    }
    root
      .querySelector<HTMLButtonElement>('[data-jc="submit"]')!
      .addEventListener("click", () => settle(collectAnswers()));
    root
      .querySelector<HTMLElement>('[data-jc="backdrop"]')!
      .addEventListener("click", () => settle(null));
  });
}

// ── Cleanup ──────────────────────────────────────────────────────────────────

/** Remove only the review panel, leaving the score badge visible. */
export function removePanel(): void {
  document.getElementById(HOST_ID)?.remove();
  _activeShadow = null;
}

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
