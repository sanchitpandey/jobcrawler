import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
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

  function storeTokens(data: LoginResponse) {
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('refresh_token', data.refresh_token)
    scheduleRefresh(data.access_token)
  }

  function scheduleRefresh(token: string) {
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
    const exp = parseJwtExpiry(token)
    if (!exp) return
    const delay = exp - Date.now() - 5 * 60 * 1000
    if (delay <= 0) return
    refreshTimer.current = setTimeout(async () => {
      const refresh = localStorage.getItem('refresh_token')
      if (!refresh) return
      try {
        const data = await api.post<LoginResponse>('/auth/refresh', { refresh_token: refresh })
        localStorage.setItem('access_token', data.access_token)
        if (data.refresh_token) localStorage.setItem('refresh_token', data.refresh_token)
        scheduleRefresh(data.access_token)
      } catch {
        logout()
      }
    }, delay)
  }

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (!token) {
      setLoading(false)
      return
    }
    api
      .get<User>('/auth/me')
      .then((u) => {
        setUser(u)
        scheduleRefresh(token)
      })
      .catch(() => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
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
    const data = await api.post<LoginResponse>('/auth/register', { email, password })
    storeTokens(data)
    const me = await api.get<User>('/auth/me')
    setUser(me)
    navigate('/verify-email')
  }

  async function verifyEmail(code: string) {
    const me = await api.post<User>('/auth/verify-email', { code })
    setUser(me)
  }

  async function resendVerification() {
    await api.post('/auth/resend-verification')
  }

  function logout() {
    if (refreshTimer.current) clearTimeout(refreshTimer.current)
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
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
