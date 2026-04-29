import { useState } from 'react'
import { api } from '../api/client'

interface RazorpayOptions {
  key: string
  amount: number
  currency: string
  name: string
  description: string
  order_id: string
  prefill: { email: string }
  theme: { color: string }
  handler: (response: Record<string, string>) => void
}

type RazorpayConstructor = new (opts: RazorpayOptions) => { open(): void }

function loadRazorpayScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    const w = window as Window & { Razorpay?: RazorpayConstructor }
    if (w.Razorpay) { resolve(); return }
    const existing = document.querySelector('script[src*="razorpay"]')
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('Razorpay SDK failed to load')))
      return
    }
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Razorpay SDK failed to load'))
    document.body.appendChild(script)
  })
}

interface Props {
  planKey: string
  label: string
  email: string
  primary?: boolean
  onSuccess: () => void
  onError: (msg: string) => void
}

export function RazorpayButton({ planKey, label, email, primary, onSuccess, onError }: Props) {
  const [loading, setLoading] = useState(false)

  async function handleClick() {
    setLoading(true)
    try {
      await loadRazorpayScript()

      const order = await api.post<{
        order_id: string
        amount: number
        currency: string
        key_id: string
        plan: string
      }>('/billing/create-order', { plan: planKey })

      const w = window as Window & { Razorpay?: RazorpayConstructor }
      if (!w.Razorpay) {
        onError('Razorpay SDK not available. Please refresh and try again.')
        return
      }

      const rzp = new w.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: 'JobCrawler',
        description: `${order.plan} plan`,
        order_id: order.order_id,
        prefill: { email },
        theme: { color: '#f59e0b' },
        handler: async (response) => {
          try {
            await api.post('/billing/verify-payment', {
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            })
            onSuccess()
          } catch {
            onError('Payment verification failed. Contact support if amount was deducted.')
          }
        },
      })
      rzp.open()
    } catch (e) {
      onError(e instanceof Error ? e.message : 'Failed to start checkout')
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      onClick={handleClick}
      disabled={loading}
      className={`h-9 rounded-lg text-sm font-semibold transition disabled:opacity-50 ${
        primary
          ? 'bg-amber text-ink hover:bg-amber2'
          : 'border border-line2 text-cream2 hover:border-cream2 hover:text-cream'
      }`}
    >
      {loading ? (
        <span className="flex items-center justify-center gap-2">
          <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
          Opening…
        </span>
      ) : (
        label
      )}
    </button>
  )
}
