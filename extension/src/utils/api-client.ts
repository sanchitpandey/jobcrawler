import { getAuthToken, setAuthToken } from "./storage.js";
import type {
  AuthToken,
  FillRequest,
  FillResponse,
  ScoreRequest,
  ScoreResponse,
} from "../types/index.js";

export const API_BASE = "http://localhost:8000";

// ── JWT helpers ───────────────────────────────────────────────────────────────

/**
 * Extract the `exp` claim from a JWT without any library.
 * JWTs are header.payload.signature where each part is base64url-encoded.
 */
function jwtExpiry(token: string): number | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    // base64url → base64 (add padding, swap - and _)
    const base64 = parts[1]
      .replace(/-/g, "+")
      .replace(/_/g, "/")
      .padEnd(Math.ceil(parts[1].length / 4) * 4, "=");
    const json = atob(base64);
    const payload = JSON.parse(json) as { exp?: number };
    return typeof payload.exp === "number" ? payload.exp : null;
  } catch {
    return null;
  }
}

/** Returns true if the token is expired or will expire within 30 seconds. */
function isExpired(token: string): boolean {
  const exp = jwtExpiry(token);
  if (exp === null) return true;
  return Math.floor(Date.now() / 1000) >= exp - 30;
}

// ── Token refresh (called internally before each API request) ─────────────────

async function doRefresh(refreshToken: string): Promise<AuthToken> {
  const response = await fetch(`${API_BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    throw new Error(`Token refresh failed: ${response.status}`);
  }
  const data = (await response.json()) as {
    access_token: string;
    refresh_token: string;
  };
  return { access_token: data.access_token, refresh_token: data.refresh_token };
}

// ── Authenticated fetch ───────────────────────────────────────────────────────

async function fetchWithAuth(path: string, body: unknown): Promise<Response> {
  let token = await getAuthToken();

  if (token && isExpired(token.access_token)) {
    try {
      token = await doRefresh(token.refresh_token);
      await setAuthToken(token);
    } catch {
      // Refresh failed — continue without a valid token; server will return 401.
    }
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token.access_token}`;
  }

  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * POST /auth/login — uses OAuth2PasswordRequestForm (form-encoded).
 * The server expects `username` (not `email`) per the OAuth2 spec.
 */
export async function login(email: string, password: string): Promise<AuthToken> {
  const formBody = new URLSearchParams({ username: email, password });
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formBody.toString(),
  });
  if (!response.ok) {
    throw new Error(`Login failed: ${response.status} ${response.statusText}`);
  }
  const data = (await response.json()) as {
    access_token: string;
    refresh_token: string;
  };
  return { access_token: data.access_token, refresh_token: data.refresh_token };
}

export async function scoreJob(request: ScoreRequest): Promise<ScoreResponse> {
  // Backend requires an `id` field — derive a stable short id from the URL.
  const id = btoa(encodeURIComponent(request.url))
    .replace(/[^A-Za-z0-9]/g, "")
    .slice(0, 64);
  const backendRequest = {
    id,
    title: request.title,
    company: request.company,
    description: request.description,
    location: "",
    is_remote: false,
  };
  const response = await fetchWithAuth("/jobs/score-job", backendRequest);
  if (!response.ok) {
    throw new Error(`scoreJob failed: ${response.status} ${response.statusText}`);
  }
  const data = (await response.json()) as {
    id: string;
    fit_score: number;
    comp_estimate: string;
    verdict: string;
    gaps: string[];
    why: string;
  };
  // Map backend field name (comp_estimate) back to the extension type (comp_est).
  return {
    fit_score: data.fit_score,
    verdict: data.verdict,
    comp_est: data.comp_estimate ?? null,
    gaps: data.gaps,
  };
}

export async function answerFields(request: FillRequest): Promise<FillResponse> {
  // Map extension field shape to backend FieldRequest (type → field_type).
  const backendRequest = {
    fields: request.fields.map((f) => ({
      label: f.label,
      field_type: f.type,
      ...(f.options !== undefined ? { options: f.options } : {}),
      ...(f.error ? { validation_error: f.error } : {}),
    })),
    company: request.company,
    job_title: request.jobTitle,
  };
  const response = await fetchWithAuth("/forms/answer-fields", backendRequest);
  if (!response.ok) {
    throw new Error(`answerFields failed: ${response.status} ${response.statusText}`);
  }
  // Backend returns an array of full AnswerItem records — pass through
  // unchanged so consumers can inspect source/confidence/manual-review flags.
  const data = (await response.json()) as FillResponse;
  return { answers: data.answers };
}

export async function generateCover(jobDescription: string): Promise<string> {
  const response = await fetchWithAuth("/forms/generate-cover", {
    company: "",
    title: "",
    location: "",
    description: jobDescription,
  });
  if (!response.ok) {
    throw new Error(`generateCover failed: ${response.status} ${response.statusText}`);
  }
  const data = (await response.json()) as { cover_letter: string };
  return data.cover_letter;
}

export interface UsageResponse {
  used: number;
  limit: number;       // -1 means unlimited (paid tier)
  resets_at: string;
  is_paid: boolean;
}

export async function getUsage(): Promise<UsageResponse> {
  const token = await getAuthToken();
  const headers: Record<string, string> = {};
  if (token) {
    headers["Authorization"] = `Bearer ${token.access_token}`;
  }
  const response = await fetch(`${API_BASE}/jobs/usage`, { headers });
  if (!response.ok) {
    throw new Error(`getUsage failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<UsageResponse>;
}
