import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function VerifyEmail() {
  const { user, verifyEmail, resendVerification } = useAuth()
  const navigate = useNavigate()
  const [digits, setDigits] = useState(['', '', '', '', '', ''])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [resendCooldown, setResendCooldown] = useState(0)
  const [resendSuccess, setResendSuccess] = useState(false)
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    if (user?.is_verified) navigate('/onboarding', { replace: true })
  }, [user, navigate])

  useEffect(() => {
    if (resendCooldown <= 0) return
    const t = setTimeout(() => setResendCooldown((c) => c - 1), 1000)
    return () => clearTimeout(t)
  }, [resendCooldown])

  function handleDigitChange(index: number, value: string) {
    const cleaned = value.replace(/\D/g, '').slice(-1)
    const next = [...digits]
    next[index] = cleaned
    setDigits(next)
    setError('')
    if (cleaned && index < 5) inputRefs.current[index + 1]?.focus()
  }

  function handleKeyDown(index: number, e: React.KeyboardEvent) {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    }
  }

  function handlePaste(e: React.ClipboardEvent) {
    e.preventDefault()
    const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6)
    if (!pasted) return
    const next = [...digits]
    pasted.split('').forEach((ch, i) => { next[i] = ch })
    setDigits(next)
    inputRefs.current[Math.min(pasted.length, 5)]?.focus()
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const code = digits.join('')
    if (code.length < 6) { setError('Enter all 6 digits'); return }
    setLoading(true)
    setError('')
    try {
      await verifyEmail(code)
      navigate('/onboarding', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid code')
      setDigits(['', '', '', '', '', ''])
      inputRefs.current[0]?.focus()
    } finally {
      setLoading(false)
    }
  }

  async function handleResend() {
    if (resendCooldown > 0) return
    try {
      await resendVerification()
      setResendCooldown(60)
      setResendSuccess(true)
      setTimeout(() => setResendSuccess(false), 4000)
    } catch {
      setError('Failed to resend code. Try again.')
    }
  }

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl border border-line2 bg-ink2/60 mb-5">
            <svg viewBox="0 0 24 24" className="w-7 h-7" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" stroke="#FF8A1F" />
            </svg>
          </div>
          <h1 className="font-serif text-3xl text-cream">Check your email</h1>
          <p className="mt-2 text-cream2 text-sm">
            We sent a 6-digit code to{' '}
            <span className="text-cream font-mono">{user?.email}</span>
          </p>
        </div>

        <form onSubmit={handleSubmit} className="border border-line2 rounded-xl bg-ink2/60 p-7 space-y-6">
          {error && (
            <div className="border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft">
              {error}
            </div>
          )}
          {resendSuccess && (
            <div className="border border-green-500/30 bg-green-500/10 rounded-lg px-4 py-3 font-mono text-xs text-green-400">
              New code sent — check your inbox.
            </div>
          )}

          <div>
            <label className="block font-mono text-[11px] uppercase tracking-wider text-cream2 mb-3">
              Verification code
            </label>
            <div className="flex gap-2 justify-between" onPaste={handlePaste}>
              {digits.map((d, i) => (
                <input
                  key={i}
                  ref={(el) => { inputRefs.current[i] = el }}
                  type="text"
                  inputMode="numeric"
                  maxLength={1}
                  value={d}
                  onChange={(e) => handleDigitChange(i, e.target.value)}
                  onKeyDown={(e) => handleKeyDown(i, e)}
                  className="w-11 h-14 rounded-lg border border-line2 bg-ink text-cream text-xl font-mono text-center focus:outline-none focus:border-amber transition"
                />
              ))}
            </div>
            <p className="mt-2 font-mono text-[11px] text-mute">Code expires in 15 minutes.</p>
          </div>

          <button
            type="submit"
            disabled={loading || digits.join('').length < 6}
            className="w-full h-11 rounded-lg bg-amber text-ink font-semibold text-sm hover:bg-amber2 disabled:opacity-50 transition"
          >
            {loading ? 'Verifying…' : 'Verify email →'}
          </button>

          <div className="text-center">
            <button
              type="button"
              onClick={handleResend}
              disabled={resendCooldown > 0}
              className="font-mono text-[11px] text-cream2 hover:text-cream disabled:text-mute transition"
            >
              {resendCooldown > 0 ? `Resend in ${resendCooldown}s` : "Didn't get it? Resend code"}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
