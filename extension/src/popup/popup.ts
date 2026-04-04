import { getUsage } from "../utils/api-client.js";
import { getAuthToken } from "../utils/storage.js";

// ── JWT decode ────────────────────────────────────────────────────────────────

/** Decode the JWT payload and return it as a plain object. */
function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = token.split(".");
  if (parts.length !== 3) return {};
  try {
    const base64 = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(parts[1].length / 4) * 4, "=");
    return JSON.parse(atob(base64)) as Record<string, unknown>;
  } catch {
    return {};
  }
}

// ── Email storage (persisted alongside auth token) ────────────────────────────

async function getStoredEmail(): Promise<string | null> {
  return new Promise((resolve) => {
    chrome.storage.local.get("user_email", (result) => {
      resolve((result["user_email"] as string) ?? null);
    });
  });
}

async function setStoredEmail(email: string): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.set({ user_email: email }, resolve);
  });
}

async function clearStoredEmail(): Promise<void> {
  return new Promise((resolve) => {
    chrome.storage.local.remove("user_email", resolve);
  });
}

// ── Service-worker message helpers ───────────────────────────────────────────

function sendLoginMessage(
  email: string,
  password: string
): Promise<void> {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(
      { type: "LOGIN", payload: { email, password } },
      (response: unknown) => {
        if (chrome.runtime.lastError) {
          reject(new Error(chrome.runtime.lastError.message));
          return;
        }
        const r = response as { type: string; payload?: { message?: string } };
        if (r?.type === "ERROR") {
          reject(new Error(r.payload?.message ?? "Login failed"));
          return;
        }
        resolve();
      }
    );
  });
}

function sendLogoutMessage(): Promise<void> {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type: "CLEAR_AUTH_TOKEN" }, () => resolve());
  });
}

// ── DOM refs ─────────────────────────────────────────────────────────────────

const loginView = document.querySelector<HTMLDivElement>("#login-view")!;
const loggedinView = document.querySelector<HTMLDivElement>("#loggedin-view")!;

const loginForm = document.querySelector<HTMLFormElement>("#login-form")!;
const emailInput = document.querySelector<HTMLInputElement>("#email-input")!;
const passwordInput = document.querySelector<HTMLInputElement>("#password-input")!;
const loginBtn = document.querySelector<HTMLButtonElement>("#login-btn")!;
const loginError = document.querySelector<HTMLParagraphElement>("#login-error")!;

const userAvatarEl = document.querySelector<HTMLDivElement>("#user-avatar")!;
const userEmailEl = document.querySelector<HTMLDivElement>("#user-email-display")!;
const userTierEl = document.querySelector<HTMLDivElement>("#user-tier-display")!;
const usageCountEl = document.querySelector<HTMLDivElement>("#usage-count")!;
const usageBarEl = document.querySelector<HTMLDivElement>("#usage-bar")!;
const usageResetEl = document.querySelector<HTMLDivElement>("#usage-reset")!;
const usageError = document.querySelector<HTMLParagraphElement>("#usage-error")!;
const logoutBtn = document.querySelector<HTMLButtonElement>("#logout-btn")!;

// ── View helpers ─────────────────────────────────────────────────────────────

function showLogin(): void {
  loginView.style.display = "block";
  loggedinView.style.display = "none";
  loginError.textContent = "";
  emailInput.value = "";
  passwordInput.value = "";
}

function showLoggedIn(email: string): void {
  loginView.style.display = "none";
  loggedinView.style.display = "block";
  userEmailEl.textContent = email;
  userAvatarEl.textContent = email.charAt(0).toUpperCase();
  usageError.textContent = "";
}

// ── Usage display ─────────────────────────────────────────────────────────────

async function loadUsage(): Promise<void> {
  try {
    const usage = await getUsage();

    const limitLabel = usage.limit === -1 ? "∞" : String(usage.limit);
    usageCountEl.innerHTML = `${usage.used} <span>/ ${limitLabel}</span>`;

    const pct =
      usage.limit === -1
        ? 0
        : Math.min(100, Math.round((usage.used / usage.limit) * 100));
    usageBarEl.style.width = `${pct}%`;

    const tierLabel = usage.is_paid ? "Paid — unlimited" : "Free tier";
    userTierEl.textContent = tierLabel;

    const resetsAt = new Date(usage.resets_at);
    const formatted = resetsAt.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
    usageResetEl.textContent = `Resets ${formatted}`;
  } catch (err) {
    usageError.textContent =
      err instanceof Error ? err.message : "Could not load usage";
  }
}

// ── Login form submit ─────────────────────────────────────────────────────────

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = emailInput.value.trim();
  const password = passwordInput.value;

  if (!email || !password) {
    loginError.textContent = "Email and password are required.";
    return;
  }

  loginBtn.disabled = true;
  loginBtn.textContent = "Signing in…";
  loginError.textContent = "";

  try {
    await sendLoginMessage(email, password);

    // Verify the stored token and decode its sub (user_id)
    const token = await getAuthToken();
    if (token) {
      const payload = decodeJwtPayload(token.access_token);
      // payload.sub is the user UUID — stored for reference
      void payload.sub;
    }

    await setStoredEmail(email);
    showLoggedIn(email);
    await loadUsage();
  } catch (err) {
    loginError.textContent =
      err instanceof Error ? err.message : "Login failed. Please try again.";
  } finally {
    loginBtn.disabled = false;
    loginBtn.textContent = "Login";
  }
});

// ── Logout ───────────────────────────────────────────────────────────────────

logoutBtn.addEventListener("click", async () => {
  await sendLogoutMessage();
  await clearStoredEmail();
  showLogin();
});

// ── Init — check existing session ─────────────────────────────────────────────

async function init(): Promise<void> {
  const [token, email] = await Promise.all([getAuthToken(), getStoredEmail()]);

  if (token && email) {
    // Decode JWT to confirm token structure (sub = user UUID)
    const payload = decodeJwtPayload(token.access_token);
    if (typeof payload.sub === "string") {
      showLoggedIn(email);
      await loadUsage();
      return;
    }
  }

  showLogin();
}

init();
