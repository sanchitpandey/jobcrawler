/**
 * Shared sender validation for chrome.runtime.onMessage listeners.
 *
 * Rationale: even though chrome.runtime.onMessage only fires for *same*-extension
 * messages (we never set externally_connectable), defence-in-depth means asserting
 * sender.id matches our extension and constraining where the message may originate.
 *
 * - `isFromOwnExtension`  — sender.id is our id, OR (legacy event with no id at all).
 * - `isFromExtensionInternal` — also requires sender.tab to be undefined (popup / SW
 *   / offscreen). Use this for messages that a malicious tab must NEVER be able
 *   to spoof to the content script (e.g. SHOW_SCORE, extract_job_details).
 */

export function isFromOwnExtension(sender: chrome.runtime.MessageSender): boolean {
  // sender.id is undefined when message comes from a content script in the same
  // extension on some Chromium builds; otherwise it carries the extension id.
  if (sender.id && sender.id !== chrome.runtime.id) return false;
  return true;
}

export function isFromExtensionInternal(sender: chrome.runtime.MessageSender): boolean {
  if (!isFromOwnExtension(sender)) return false;
  // Popup, SW, and offscreen documents have no associated tab.
  return sender.tab === undefined;
}
