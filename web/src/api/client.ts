// In development VITE_API_URL=/api — requests go through Vite's proxy to localhost:8000.
// In production VITE_API_URL=https://api.jobcrawler.io — direct HTTPS, FastAPI CORS handles it.
const API_BASE: string = import.meta.env.VITE_API_URL ?? '/api'

// ── Token storage ─────────────────────────────────────────────────────────────
//
// Access token  : in-memory only. Lost on full page reload; AuthContext rehydrates
//                 it via /auth/refresh (cookie-backed) at startup, so the UX is
//                 unchanged but XSS can no longer exfiltrate the token.
// Refresh token : NEVER read by JS. Lives in an httpOnly+SameSite=Strict cookie
//                 set by the API on /auth/login and /auth/refresh, scoped to /auth.

let accessToken: string | null = null

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getAccessToken(): string | null {
  return accessToken
}

function authHeaders(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  }
}

async function tryRefresh(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',  // send the httpOnly refresh cookie
      body: JSON.stringify({}),
    })
    if (!res.ok) return false
    const data = await res.json()
    accessToken = data.access_token
    return true
  } catch {
    return false
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`
  // `credentials: 'include'` is needed so the browser sends the refresh cookie
  // on /auth/* paths. For other paths it's harmless.
  const res = await fetch(url, {
    ...options,
    credentials: 'include',
    headers: { ...authHeaders(), ...(options.headers ?? {}) },
  })

  if (res.status === 401) {
    // Only attempt refresh + redirect when we actually had a session token.
    // Without a token (e.g. a failed login attempt) this is a normal API error —
    // fall through so the caller receives the error message from the response body.
    if (accessToken) {
      const refreshed = await tryRefresh()
      if (refreshed) {
        const retry = await fetch(url, {
          ...options,
          credentials: 'include',
          headers: { ...authHeaders(), ...(options.headers ?? {}) },
        })
        if (!retry.ok) {
          accessToken = null
          window.location.href = '/login'
          throw new Error('Session expired')
        }
        return retry.json() as Promise<T>
      }
      accessToken = null
      window.location.href = '/login'
      throw new Error('Session expired')
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    const raw = err.detail
    // FastAPI validation errors return detail as an array of {msg, loc} objects
    const message =
      typeof raw === 'string'
        ? raw
        : Array.isArray(raw)
          ? raw.map((e: { msg?: string }) => e.msg ?? 'Validation error').join('; ')
          : 'Request failed'
    throw new Error(message)
  }

  const text = await res.text()
  return text ? (JSON.parse(text) as T) : ({} as T)
}

export const api = {
  get: <T>(path: string) => request<T>(path),

  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'POST',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: 'PATCH',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    }),

  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),

  /** Attempt a silent refresh — used on app boot to rehydrate the access token. */
  refresh: tryRefresh,
}
