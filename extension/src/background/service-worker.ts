import { getAuthToken, setAuthToken, clearAuthToken } from "../utils/storage.js";
import { login, scoreJob, answerFields, generateCover } from "../utils/api-client.js";
import type { Message } from "../types/index.js";

// ── First-install hook ────────────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === chrome.runtime.OnInstalledReason.INSTALL) {
    // openPopup() requires a user gesture in some Chrome builds; suppress error.
    chrome.action.openPopup().catch(() => undefined);
  }
});

// ── Message bus ───────────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener(
  (message: Message, _sender, sendResponse) => {
    handleMessage(message)
      .then(sendResponse)
      .catch((err: unknown) => {
        sendResponse({ type: "ERROR", payload: { message: String(err) } });
      });
    return true; // keep channel open for async response
  }
);

async function handleMessage(message: Message): Promise<unknown> {
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

    case "GET_AUTH_TOKEN":
      return { type: "AUTH_TOKEN_RESULT", payload: await getAuthToken() };

    case "CLEAR_AUTH_TOKEN":
      await clearAuthToken();
      return { type: "AUTH_TOKEN_RESULT", payload: null };

    default:
      return { type: "ERROR", payload: { message: "Unknown message type" } };
  }
}
