import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center px-4">
      <link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />

      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <Link to="/" className="inline-flex items-center gap-2 mb-6">
            <span className="relative w-7 h-7 inline-flex items-center justify-center">
              <span className="absolute inset-0 rounded-md border border-line2" />
              <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7">
                <circle cx="12" cy="12" r="3.2" stroke="#FF8A1F" />
                <path d="M12 8.8V4M12 15.2V20M8.8 12H4M15.2 12H20M9.7 9.7L6.3 6.3M14.3 9.7L17.7 6.3M9.7 14.3L6.3 17.7M14.3 14.3L17.7 17.7" stroke="#EDE6D6" />
              </svg>
            </span>
            <span className="font-semibold tracking-tight text-[15px] text-cream">JobCrawler</span>
          </Link>
          <h1 className="font-serif text-4xl text-cream">Welcome back.</h1>
          <p className="mt-2 text-cream2 text-sm">Sign in to your account to continue.</p>
        </div>

        <form onSubmit={handleSubmit} className="border border-line2 rounded-xl bg-ink2/60 p-7 space-y-5">
          {error && (
            <div className="border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft space-y-1">
              <div>{error}</div>
              {error.toLowerCase().includes('incorrect') && (
                <div className="text-mute">
                  No account?{' '}
                  <Link to="/register" className="text-amber hover:underline underline-offset-2">
                    Create one free →
                  </Link>
                </div>
              )}
            </div>
          )}

          <div className="space-y-1.5">
            <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="you@example.com"
              className="w-full h-11 px-3 rounded-lg border border-line2 bg-ink text-cream text-sm placeholder:text-mute focus:outline-none focus:border-amber transition"
            />
          </div>

          <div className="space-y-1.5">
            <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              placeholder="••••••••"
              className="w-full h-11 px-3 rounded-lg border border-line2 bg-ink text-cream text-sm placeholder:text-mute focus:outline-none focus:border-amber transition"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full h-11 rounded-lg bg-amber text-ink font-semibold text-sm hover:bg-amber2 disabled:opacity-50 transition"
          >
            {loading ? 'Signing in…' : 'Sign in →'}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-cream2">
          Don't have an account?{' '}
          <Link to="/register" className="text-amber hover:underline underline-offset-4">
            Create one free
          </Link>
        </p>
      </div>
    </div>
  )
}
