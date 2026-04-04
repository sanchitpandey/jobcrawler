import type { AuthToken } from "../types/index.js";

const AUTH_TOKEN_KEY = "auth_token";

export async function getAuthToken(): Promise<AuthToken | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get(AUTH_TOKEN_KEY, (result) => {
      resolve((result[AUTH_TOKEN_KEY] as AuthToken) ?? null);
    });
  });
}

export async function setAuthToken(token: AuthToken): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({ [AUTH_TOKEN_KEY]: token }, resolve);
  });
}

export async function clearAuthToken(): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.remove(AUTH_TOKEN_KEY, resolve);
  });
}
