/**
 * Shared sender validation for chrome.runtime.onMessage listeners.
 *
 * Rationale: even though chrome.runtime.onMessage only fires for *same*-extension
 * messages (we never set externally_connectable), defence-in-depth means asserting
 * sender.id matches our extension and constraining where the message may originate.
 *
 * - `isFromOwnExtension`  — sender.id must equal our id. (Audit N14: prior
 *   logic short-circuited on `undefined`, which Chromium does not produce for
 *   same-extension messages but would let a future MV3 quirk slip through.)
 * - `isFromExtensionInternal` — also requires sender.tab to be undefined (popup / SW
 *   / offscreen). Use this for messages that a malicious tab must NEVER be able
 *   to spoof to the content script (e.g. SHOW_SCORE, extract_job_details).
 */

export function isFromOwnExtension(sender: chrome.runtime.MessageSender): boolean {
  // Strict equality: refuse missing or mismatched ids. Current Chromium
  // populates sender.id for every same-extension message — anything else is
  // either a foreign extension (would already be blocked by Chrome before this
  // point) or a malformed/forged event.
  return sender.id === chrome.runtime.id;
}

export function isFromExtensionInternal(sender: chrome.runtime.MessageSender): boolean {
  if (!isFromOwnExtension(sender)) return false;
  // Popup, SW, and offscreen documents have no associated tab.
  return sender.tab === undefined;
}
