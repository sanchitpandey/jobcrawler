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

import * as linkedinHandler from "./sites/linkedin.js";
import * as indeedHandler from "./sites/indeed.js";
import * as greenhouseHandler from "./sites/greenhouse.js";
import * as leverHandler from "./sites/lever.js";

async function loadHandler(platform: string): Promise<SiteHandler | null> {
  switch (platform) {
    case "linkedin":   return linkedinHandler;
    case "indeed":     return indeedHandler;
    case "greenhouse": return greenhouseHandler;
    case "lever":      return leverHandler;
    default:           return null; // ashby / workday / icims: overlay only
  }
}

// ── SHOW_SCORE message from the service worker ────────────────────────────────

chrome.runtime.onMessage.addListener((message: Message): void => {
  if (message.type === "SHOW_SCORE") {
    // Suppress score overlay in batch mode — no user is watching.
    chrome.storage.local.get("batchMode").then(({ batchMode }) => {
      if (!batchMode) showOverlay(message.payload);
    }).catch(() => undefined);
  }
});

// ── Main ─────────────────────────────────────────────────────────────────────

function main(): void {
  const match = detectATS(window.location.href);
  if (!match) return;

  console.log(
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
