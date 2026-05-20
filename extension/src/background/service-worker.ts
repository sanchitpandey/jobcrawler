import { getAuthToken, setAuthToken, clearAuthToken } from "../utils/storage.js";
import {
  login,
  scoreJob,
  answerFields,
  generateCover,
  trackJob,
  updateStatus,
} from "../utils/api-client.js";
import { discoveryOrchestrator } from "./discovery-orchestrator.js";
import { autoApplyOrchestrator } from "./auto-apply-orchestrator.js";
import type { Message } from "../types/index.js";

// ── Service-worker keepalive (MV3 workers die after ~5 min idle) ──────────────

chrome.alarms.onAlarm.addListener((_alarm) => {
  // No-op: receiving the alarm event is enough to keep the worker alive.
});

// ── Startup / install cleanup ─────────────────────────────────────────────────
// Clear any flags that may have been left behind if the browser was closed
// mid-session (e.g. batchMode=true while applying, or a stale discoveryStatus).

function clearStaleSessionFlags(): void {
  chrome.storage.local
    .set({ batchMode: false, currentJobId: null })
    .catch(() => undefined);
}

chrome.runtime.onStartup.addListener(clearStaleSessionFlags);

chrome.runtime.onInstalled.addListener((details) => {
  clearStaleSessionFlags();
  if (details.reason === chrome.runtime.OnInstalledReason.INSTALL) {
    // openPopup() requires a user gesture in some Chrome builds; suppress error.
    chrome.action.openPopup().catch(() => undefined);
  }
});

// ── Message bus ───────────────────────────────────────────────────────────────

// Origins allowed to send content-script messages to the SW. Must align with
// host_permissions/content_scripts in manifest.json. The webapp is excluded —
// it talks to the API directly over HTTPS, never to the extension SW.
const ALLOWED_CONTENT_ORIGINS: readonly RegExp[] = [
  /^https:\/\/www\.linkedin\.com$/,
  /^https:\/\/([a-z0-9-]+\.)?indeed\.com$/,
  /^https:\/\/(boards\.|[a-z0-9-]+\.)?greenhouse\.io$/,
  /^https:\/\/grnh\.se$/,
  /^https:\/\/(jobs\.|[a-z0-9-]+\.)?lever\.co$/,
  /^https:\/\/[a-z0-9-]+\.ashbyhq\.com$/,
  /^https:\/\/[a-z0-9-]+\.myworkdayjobs\.com$/,
  /^https:\/\/[a-z0-9-]+\.icims\.com$/,
];

// Messages that only the popup/options/SW itself is allowed to send.
// Receiving these from a content-script frame would be a privilege escalation.
const POPUP_ONLY_MESSAGES = new Set([
  "LOGIN",
  "CLEAR_AUTH_TOKEN",
  "GET_AUTH_TOKEN",
  "start_discovery",
  "stop_discovery",
  "start_auto_apply",
  "stop_auto_apply",
]);

// Messages that may only originate from a content script on an allowlisted tab.
const CONTENT_ONLY_MESSAGES = new Set([
  "batch_job_complete",
  "batch_job_failed",
  "discovery_page_complete",
]);

function isAllowedContentOrigin(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const origin = new URL(url).origin;
    return ALLOWED_CONTENT_ORIGINS.some((re) => re.test(origin));
  } catch {
    return false;
  }
}

function validateSender(message: Message, sender: chrome.runtime.MessageSender): string | null {
  // 1. Cross-extension messages are always rejected. chrome.runtime.onMessage
  //    only fires for same-extension messages when externally_connectable is
  //    unset (it is), but we defend in depth.
  if (sender.id && sender.id !== chrome.runtime.id) {
    return "untrusted extension";
  }
  // 2. Popup / options / service-worker self has no sender.tab.
  const fromTab = sender.tab !== undefined;
  if (POPUP_ONLY_MESSAGES.has(message.type) && fromTab) {
    return "tab cannot send popup-only message";
  }
  // 3. Content-originated messages must come from an allowlisted origin.
  if (CONTENT_ONLY_MESSAGES.has(message.type)) {
    if (!fromTab || !isAllowedContentOrigin(sender.tab?.url ?? sender.url)) {
      return "content message from non-allowlisted origin";
    }
  }
  return null;
}

chrome.runtime.onMessage.addListener(
  (message: Message, sender, sendResponse) => {
    const reject = validateSender(message, sender);
    if (reject) {
      console.warn("[JobCrawler] dropping message:", reject, message.type, sender.url);
      try { sendResponse({ type: "ERROR", payload: { message: "forbidden" } }); } catch { /* port closed */ }
      return false;
    }
    handleMessage(message, sender)
      .then((result) => {
        // Port may already be closed if popup navigated away — suppress the error.
        try { sendResponse(result); } catch { /* port closed */ }
      })
      .catch((err: unknown) => {
        try {
          sendResponse({ type: "ERROR", payload: { message: String(err) } });
        } catch { /* port closed */ }
      });
    return true; // keep channel open for async response
  }
);

async function handleMessage(message: Message, sender?: chrome.runtime.MessageSender): Promise<unknown> {
  switch (message.type) {
    case "LOGIN": {
      const token = await login(message.payload.email, message.payload.password);
      await setAuthToken(token);
      return { type: "LOGIN_RESULT", payload: token };
    }

    case "SCORE_JOB":
      return {
        type: "SCORE_JOB_RESULT",
        payload: await scoreJob(message.payload),
      };

    case "ANSWER_FIELDS":
      return {
        type: "ANSWER_FIELDS_RESULT",
        payload: await answerFields(message.payload),
      };

    case "GENERATE_COVER": {
      const cover_letter = await generateCover(message.payload.jobDescription);
      return { type: "GENERATE_COVER_RESULT", payload: { cover_letter } };
    }

    case "TRACK_JOB": {
      const result = await trackJob(message.payload);
      return { type: "TRACK_JOB_RESULT", payload: result };
    }

    case "UPDATE_STATUS": {
      const result = await updateStatus(message.payload);
      return { type: "UPDATE_STATUS_RESULT", payload: result };
    }

    case "GET_AUTH_TOKEN":
      return { type: "AUTH_TOKEN_RESULT", payload: await getAuthToken() };

    case "CLEAR_AUTH_TOKEN":
      await clearAuthToken();
      return { type: "AUTH_TOKEN_RESULT", payload: null };

    case "start_discovery":
      // Fire-and-forget: the orchestrator sends progress updates independently.
      discoveryOrchestrator.start(message.payload).catch(() => undefined);
      return { ok: true };

    case "stop_discovery":
      discoveryOrchestrator.stop();
      return { ok: true };

    // discovery_page_complete is handled internally by the orchestrator's
    // own onMessage listener inside runDiscoveryScrape(). Acknowledge here
    // so callers don't receive an "unknown message type" error.
    case "discovery_page_complete":
    case "discovery_progress":
      return { ok: true };

    case "start_auto_apply":
      autoApplyOrchestrator.start(message.payload?.maxJobs).catch(() => undefined);
      return { ok: true };

    case "stop_auto_apply":
      autoApplyOrchestrator.stop();
      return { ok: true };

    case "batch_job_complete":
      autoApplyOrchestrator.handleBatchJobComplete(message, sender?.tab?.id ?? -1);
      return { ok: true };

    case "batch_job_failed":
      autoApplyOrchestrator.handleBatchJobFailed(message.error, sender?.tab?.id ?? -1);
      return { ok: true };

    // auto_apply_progress is broadcast outward to popup; acknowledge if received.
    case "auto_apply_progress":
      return { ok: true };

    default:
      return { type: "ERROR", payload: { message: "Unknown message type" } };
  }
}
