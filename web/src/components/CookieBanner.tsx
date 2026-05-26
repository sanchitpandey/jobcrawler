import { useState } from 'react'
import { Link } from 'react-router-dom'

const CONSENT_KEY = 'jc_cookie_consent'

type Consent = 'all' | 'essential'

export function getStoredConsent(): Consent | null {
  const v = localStorage.getItem(CONSENT_KEY)
  return v === 'all' || v === 'essential' ? v : null
}

export function CookieBanner() {
  const [visible, setVisible] = useState<boolean>(() => getStoredConsent() === null)

  function accept(value: Consent) {
    localStorage.setItem(CONSENT_KEY, value)
    setVisible(false)
  }

  if (!visible) return null

  return (
    <div
      role="dialog"
      aria-label="Cookie preferences"
      className="fixed bottom-0 inset-x-0 z-50 border-t border-line2 bg-ink/95 backdrop-blur-sm px-6 py-4"
    >
      <div className="max-w-5xl mx-auto flex flex-col sm:flex-row sm:items-center gap-4">
        <p className="text-sm text-cream2 flex-1 leading-relaxed">
          We use{' '}
          <span className="text-cream font-medium">strictly necessary cookies</span> for authentication
          (session &amp; CSRF protection). When you use billing features, Razorpay's checkout may set
          third-party analytics cookies.{' '}
          <Link to="/privacy#cookies" className="text-amber hover:text-amber2 underline underline-offset-2">
            Cookie details
          </Link>
        </p>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={() => accept('essential')}
            className="h-9 px-4 rounded-lg border border-line2 text-cream2 text-sm hover:border-cream2 hover:text-cream transition"
          >
            Essential only
          </button>
          <button
            onClick={() => accept('all')}
            className="h-9 px-5 rounded-lg bg-amber text-ink text-sm font-semibold hover:bg-amber2 transition"
          >
            Accept all
          </button>
        </div>
      </div>
    </div>
  )
}
