/**
 * orchestrator.ts
 *
 * Main content script entry point.
 * Detects the ATS platform, hands off to the right site handler, injects the
 * score overlay, and listens for SHOW_SCORE messages from the service worker.
 *
 * All site-specific logic lives in ./sites/<platform>.ts — this file stays thin.
 */

import { detectATS } from "./ats-detector.js";
import { showOverlay } from "../overlay/overlay.js";
import type { Message } from "../types/index.js";

// ── Site handler interface ────────────────────────────────────────────────────

interface SiteHandler {
  init(): void;
}

/**
 * Resolve the right handler module for a detected platform.
 * Dynamic imports are inlined by esbuild (no splitting needed) while still
 * keeping each handler in its own source file.
 */
async function loadHandler(platform: string): Promise<SiteHandler | null> {
  switch (platform) {
    case "linkedin":   return import("./sites/linkedin.js");
    case "indeed":     return import("./sites/indeed.js");
    case "greenhouse": return import("./sites/greenhouse.js");
    case "lever":      return import("./sites/lever.js");
    default:           return null; // ashby / workday / icims: overlay only
  }
}

// ── SHOW_SCORE message from the service worker ────────────────────────────────

chrome.runtime.onMessage.addListener((message: Message): void => {
  if (message.type === "SHOW_SCORE") {
    showOverlay(message.payload);
  }
});

// ── Main ─────────────────────────────────────────────────────────────────────

function main(): void {
  const match = detectATS(window.location.href);
  if (!match) return;

  console.debug(
    `[JobCrawler] ${match.platform} detected (difficulty: ${match.difficulty})`
  );

  loadHandler(match.platform)
    .then((handler) => { if (handler) handler.init(); })
    .catch((err: unknown) => {
      console.error("[JobCrawler] site handler failed to load:", err);
    });
}

// Run after DOM is ready — content scripts run at document_idle by default,
// but guard against the edge case of being injected earlier.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", main, { once: true });
} else {
  main();
}
