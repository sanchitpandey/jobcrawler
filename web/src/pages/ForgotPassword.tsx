import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'

export function ForgotPassword() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.post('/auth/forgot-password', { email })
      // Audit fix #21: pass email via router state instead of a query string
      // so it doesn't land in browser history / Referer / analytics.
      navigate('/reset-password', { state: { email } })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
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
          <h1 className="font-serif text-4xl text-cream">Reset password.</h1>
          <p className="mt-2 text-cream2 text-sm">We'll email you a 6-digit code.</p>
        </div>

        <form onSubmit={handleSubmit} className="border border-line2 rounded-xl bg-ink2/60 p-7 space-y-5">
          {error && (
            <div className="border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft">
              {error}
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

          <button
            type="submit"
            disabled={loading}
            className="w-full h-11 rounded-lg bg-amber text-ink font-semibold text-sm hover:bg-amber2 disabled:opacity-50 transition"
          >
            {loading ? 'Sending…' : 'Send reset code →'}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-cream2">
          Remember it?{' '}
          <Link to="/login" className="text-amber hover:underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}
