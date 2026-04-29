import { useState, useEffect } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { RazorpayButton } from '../components/RazorpayButton'

interface BillingStatus {
  tier: string
  plan: string | null
  expires_at: string | null
  is_active: boolean
  applications_this_week?: number
  weekly_limit?: number
}

const PLANS = [
  {
    key: 'monthly',
    label: 'Monthly',
    price: '₹499',
    period: '/month',
    desc: 'Billed monthly. Cancel anytime.',
    primary: false,
    features: ['Unlimited applications', 'Priority LLM scoring', 'All job boards'],
  },
  {
    key: 'annual',
    label: 'Annual',
    price: '₹4,999',
    period: '/year',
    desc: 'Save 17% vs monthly.',
    badge: 'Best value',
    primary: true,
    features: ['Everything in Monthly', 'Early access to new features', 'Priority support'],
  },
]

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-3.5 h-3.5 text-green shrink-0" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  )
}

export function Billing() {
  const { user } = useAuth()
  const [status, setStatus] = useState<BillingStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  function load() {
    setLoading(true)
    api
      .get<BillingStatus>('/billing/status')
      .then(setStatus)
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(load, [])

  const isPro = status?.tier === 'paid'
  const email = user?.email ?? ''

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-6">
        <h1 className="font-serif text-[2rem] text-cream">Billing</h1>
        <p className="text-cream2 text-sm mt-1">Manage your subscription and payment details.</p>
      </div>

      {error && (
        <div className="mb-5 border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft">
          {error}
        </div>
      )}

      {/* Current plan card */}
      {!loading && (
        <div
          className={`mb-8 border rounded-xl px-5 py-4 ${
            isPro ? 'border-green/25 bg-green/5' : 'border-line2 bg-ink2/30'
          }`}
        >
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <p className="text-sm font-medium text-cream">
                Current plan:{' '}
                <span className={isPro ? 'text-green' : 'text-mute capitalize'}>
                  {isPro ? 'Pro' : 'Free'}
                </span>
              </p>
              {isPro && status?.expires_at && (
                <p className="text-xs text-cream2">
                  Active until{' '}
                  {new Date(status.expires_at).toLocaleDateString('en-IN', {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric',
                  })}
                </p>
              )}
              {!isPro && (
                <p className="text-xs text-mute">
                  Free plan: 10 applications/week. Upgrade for unlimited.
                </p>
              )}
            </div>
            {isPro && (
              <span className="font-mono text-[11px] px-2.5 py-1 rounded-full border border-green/25 bg-green/10 text-green">
                Active
              </span>
            )}
          </div>

          {/* Usage */}
          <div className="mt-4 pt-4 border-t border-line2/50">
            <p className="font-mono text-[11px] uppercase tracking-wider text-mute mb-2">
              Usage this week
            </p>
            {isPro ? (
              <p className="text-sm text-cream2">
                <span className="text-green font-medium">Unlimited</span> applications
              </p>
            ) : (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs text-cream2">
                  <span>
                    {status?.applications_this_week ?? 0} / {status?.weekly_limit ?? 10} applications
                  </span>
                  <span className="text-mute">
                    {Math.max(0, (status?.weekly_limit ?? 10) - (status?.applications_this_week ?? 0))} remaining
                  </span>
                </div>
                <div className="h-1.5 bg-line2 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-amber rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, ((status?.applications_this_week ?? 0) / (status?.weekly_limit ?? 10)) * 100)}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Free tier — upgrade */}
      {!isPro && (
        <div className="space-y-4">
          <p className="font-mono text-[11px] uppercase tracking-wider text-cream2">Upgrade to Pro</p>
          <div className="grid grid-cols-2 gap-4">
            {PLANS.map((plan) => (
              <div
                key={plan.key}
                className={`border rounded-xl p-5 flex flex-col ${
                  plan.primary ? 'border-amber/30 bg-amber/3' : 'border-line2'
                }`}
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <p className="font-medium text-cream">{plan.label}</p>
                    <p className="text-xs text-mute mt-0.5">{plan.desc}</p>
                  </div>
                  {'badge' in plan && plan.badge && (
                    <span className="font-mono text-[9px] px-2 py-0.5 rounded-full bg-amber/15 text-amber border border-amber/20">
                      {plan.badge}
                    </span>
                  )}
                </div>

                <div className="mb-4">
                  <span className="font-mono text-2xl text-cream">{plan.price}</span>
                  <span className="text-mute text-sm">{plan.period}</span>
                </div>

                <ul className="space-y-1.5 mb-5 flex-1">
                  {plan.features.map((f, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs text-cream2">
                      <CheckIcon />
                      {f}
                    </li>
                  ))}
                </ul>

                <RazorpayButton
                  planKey={plan.key}
                  label={`Get ${plan.label}`}
                  email={email}
                  primary={plan.primary}
                  onSuccess={() => { load() }}
                  onError={(msg) => setError(msg)}
                />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pro tier — management */}
      {isPro && (
        <div className="border border-line2 rounded-xl p-5 space-y-4">
          <p className="font-mono text-[11px] uppercase tracking-wider text-cream2">
            Subscription Management
          </p>

          {status?.expires_at && (
            <p className="text-sm text-cream2">
              Your plan renews on{' '}
              <span className="text-cream">
                {new Date(status.expires_at).toLocaleDateString('en-IN', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </span>
            </p>
          )}

          <div className="pt-2 border-t border-line2/50">
            <p className="text-xs text-mute mb-3">
              Cancelling will keep Pro access until the end of your billing period.
            </p>
            <button
              onClick={() => setError('Cancellation is not yet available via web. Please contact support.')}
              className="h-9 px-4 rounded-lg border border-red-soft/30 text-red-soft text-sm hover:bg-red-soft/10 transition"
            >
              Cancel Subscription
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
