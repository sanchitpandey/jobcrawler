/**
 * overlay.ts
 *
 * Injects a fixed-position score badge into the host page DOM.
 * Collapsed badge shows score circle + verdict + comp_est.
 * Click the badge body to toggle the gaps panel.
 * Click ✕ to dismiss.
 */

import type { ScoreResponse } from "../types/index.js";

const OVERLAY_ID = "jc-overlay";
let expanded = false;

// ── Helpers ───────────────────────────────────────────────────────────────────

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function scoreColor(n: number): string {
  if (n >= 70) return "#22c55e"; // green
  if (n >= 50) return "#f59e0b"; // yellow/amber
  return "#ef4444";              // red
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Inject (or replace) the score overlay.
 * Idempotent — calling twice removes the previous overlay first.
 */
export function showOverlay(score: ScoreResponse): void {
  hideOverlay(); // remove any existing instance before creating a fresh one
  expanded = false;

  const color = scoreColor(score.fit_score);

  const el = document.createElement("div");
  el.id = OVERLAY_ID;

  Object.assign(el.style, {
    all:          "initial",           // reset host-page cascade
    position:     "fixed",
    bottom:       "20px",
    right:        "20px",
    zIndex:       "999999",
    fontFamily:   "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    fontSize:     "13px",
    lineHeight:   "1.4",
    background:   "#1e1e2e",
    color:        "#e2e8f0",
    borderRadius: "10px",
    boxShadow:    "0 4px 24px rgba(0,0,0,0.55)",
    minWidth:     "220px",
    maxWidth:     "300px",
    overflow:     "hidden",
    cursor:       "default",
    userSelect:   "none",
  });

  // ── Score circle ────────────────────────────────────────────────────────────
  const circleHtml = `
    <div style="
      width:42px; height:42px; border-radius:50%;
      border:2px solid ${color};
      background:${color}1a;
      display:flex; align-items:center; justify-content:center;
      font-size:14px; font-weight:700; color:${color}; flex-shrink:0;
    ">${score.fit_score}</div>`;

  // ── Verdict + comp_est row ──────────────────────────────────────────────────
  const verdictHtml = `
    <div style="font-weight:600; color:#f1f5f9; font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
      ${escapeHtml(score.verdict)}
    </div>`;

  const compHtml = score.comp_est
    ? `<div style="font-size:12px; color:#94a3b8; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
         ${escapeHtml(score.comp_est)}
       </div>`
    : "";

  // ── Gaps panel (hidden until expanded) ─────────────────────────────────────
  const gapItems = score.gaps
    .map((g) => `<li style="margin-bottom:4px">${escapeHtml(g)}</li>`)
    .join("");

  const gapsPanelHtml = gapItems
    ? `<div id="jc-gaps" style="
         padding:0 14px 12px 14px;
         border-top:1px solid #2e2e42;
         display:none;
       ">
         <div style="
           font-size:11px; font-weight:600; color:#64748b;
           text-transform:uppercase; letter-spacing:.06em;
           margin:10px 0 6px;
         ">Gaps</div>
         <ul style="
           margin:0; padding:0 0 0 16px; list-style:disc;
           color:#fca5a5; font-size:12px; line-height:1.5;
         ">${gapItems}</ul>
       </div>`
    : "";

  // ── Expand hint (only if there are gaps) ───────────────────────────────────
  const hintHtml = gapItems
    ? `<div id="jc-hint" style="
         font-size:11px; color:#475569; margin-top:3px; white-space:nowrap;
       ">▾ tap for gaps</div>`
    : "";

  el.innerHTML = `
    <div id="jc-header" style="
      display:flex; align-items:center; gap:10px; padding:12px 14px;
      cursor:${gapItems ? "pointer" : "default"};
    ">
      ${circleHtml}
      <div style="flex:1; min-width:0;">
        ${verdictHtml}
        ${compHtml}
        ${hintHtml}
      </div>
      <button id="jc-close" style="
        all:unset; color:#475569; cursor:pointer; font-size:15px;
        line-height:1; padding:0 0 0 8px; flex-shrink:0;
        display:flex; align-items:center;
      " title="Dismiss">✕</button>
    </div>
    ${gapsPanelHtml}
  `;

  document.body.appendChild(el);

  // ── Wire up interactions ────────────────────────────────────────────────────

  const header = el.querySelector<HTMLElement>("#jc-header")!;
  const gapsDiv = el.querySelector<HTMLElement>("#jc-gaps");
  const hintEl = el.querySelector<HTMLElement>("#jc-hint");
  const closeBtn = el.querySelector<HTMLElement>("#jc-close")!;

  if (gapsDiv) {
    header.addEventListener("click", (e) => {
      if (closeBtn.contains(e.target as Node)) return;
      expanded = !expanded;
      gapsDiv.style.display = expanded ? "block" : "none";
      if (hintEl) hintEl.textContent = expanded ? "▴ collapse" : "▾ tap for gaps";
    });
  }

  closeBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    hideOverlay();
  });
}

/** Remove the overlay from the page. Safe to call when no overlay exists. */
export function hideOverlay(): void {
  document.getElementById(OVERLAY_ID)?.remove();
  expanded = false;
}
