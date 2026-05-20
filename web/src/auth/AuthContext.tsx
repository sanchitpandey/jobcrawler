import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setAccessToken } from '../api/client'
import type { User, LoginResponse } from '../api/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  verifyEmail: (code: string) => Promise<void>
  resendVerification: () => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

function parseJwtExpiry(token: string): number | null {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Access token lives in memory only (set by api/client). Refresh token is the
  // httpOnly cookie set by the API — never visible to JS.
  function storeTokens(data: LoginResponse) {
    setAccessToken(data.access_token)
    scheduleRefresh(data.access_token)
  }

  function scheduleRefresh(token: string) {
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
    const exp = parseJwtExpiry(token)
    if (!exp) return
    const delay = exp - Date.now() - 5 * 60 * 1000
    if (delay <= 0) return
    refreshTimer.current = setTimeout(async () => {
      // The httpOnly refresh cookie is sent automatically.
      const ok = await api.refresh()
      if (!ok) {
        logout()
        return
      }
      // After a successful refresh, fetch a fresh access token expiry.
      try {
        const me = await api.get<User>('/auth/me')
        setUser(me)
      } catch {
        logout()
      }
    }, delay)
  }

  useEffect(() => {
    // On boot, try a silent refresh against the cookie. If the server has a
    // valid refresh row, we get a fresh access token without any user action.
    api
      .refresh()
      .then((ok) => {
        if (!ok) {
          setLoading(false)
          return
        }
        return api
          .get<User>('/auth/me')
          .then((u) => setUser(u))
          .catch(() => undefined)
      })
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function login(email: string, password: string) {
    const data = await api.post<LoginResponse>('/auth/login', { email, password })
    storeTokens(data)
    const me = await api.get<User>('/auth/me')
    setUser(me)
    navigate('/dashboard')
  }

  async function register(email: string, password: string) {
    // Registration now returns 202 with no tokens (fix #9: no user enumeration).
    // The user must check their email and click /verify-email before logging in.
    await api.post('/auth/register', { email, password })
    navigate(`/login?verify=1&email=${encodeURIComponent(email)}`)
  }

  async function verifyEmail(code: string) {
    const me = await api.post<User>('/auth/verify-email', { code })
    setUser(me)
  }

  async function resendVerification() {
    await api.post('/auth/resend-verification')
  }

  async function logout() {
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
    try {
      // Best-effort: revoke the server-side refresh row + clear the cookie.
      await api.post('/auth/logout')
    } catch {
      /* ignore */
    }
    setAccessToken(null)
    setUser(null)
    navigate('/login')
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, verifyEmail, resendVerification, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
