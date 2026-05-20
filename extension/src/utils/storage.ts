import type { AuthToken } from "../types/index.js";

/**
 * Token storage strategy
 * ----------------------
 *
 * Refresh tokens are sensitive — they're long-lived and grant new access
 * tokens for the duration of their lifetime. Storing them in
 * `chrome.storage.local` was a defence-in-depth gap: any extension content
 * script with broad host permissions (or any extension page bug) could read
 * the entire object.
 *
 * We now use `chrome.storage.session` — an MV3-only area that is:
 *   - in-memory only (cleared when the browser closes)
 *   - not accessible to content scripts by default (must explicitly grant
 *     TRUSTED_AND_UNTRUSTED_CONTEXTS access), which we never do.
 *
 * This means only the service worker, popup, and offscreen document can read
 * the token. A page with our content script injected cannot.
 *
 * Trade-off: the user has to re-authenticate after a full browser restart.
 * That's an acceptable UX cost for an aggressive automation extension.
 */

const AUTH_TOKEN_KEY = "auth_token";

// `chrome.storage.session` was added in Chrome 102. Fall back to `local` only
// if the runtime is too old to support it — but the manifest already targets
// MV3 (Chrome ≥ 88) and `session` is broadly available.
function area(): chrome.storage.StorageArea {
  return (chrome.storage as unknown as { session?: chrome.storage.StorageArea }).session
    ?? chrome.storage.local;
}

export async function getAuthToken(): Promise<AuthToken | null> {
  return new Promise((resolve) => {
    area().get(AUTH_TOKEN_KEY, (result) => {
      resolve((result[AUTH_TOKEN_KEY] as AuthToken) ?? null);
    });
  });
}

export async function setAuthToken(token: AuthToken): Promise<void> {
  return new Promise((resolve) => {
    area().set({ [AUTH_TOKEN_KEY]: token }, () => resolve());
  });
}

export async function clearAuthToken(): Promise<void> {
  return new Promise((resolve) => {
    area().remove(AUTH_TOKEN_KEY, () => resolve());
    // Also scrub any token left in `local` from a previous version of this
    // extension — one-time migration.
    chrome.storage.local.remove(AUTH_TOKEN_KEY, () => undefined);
  });
}
