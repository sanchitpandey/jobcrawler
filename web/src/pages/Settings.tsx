import { useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../auth/AuthContext'

// ── Shared UI ──────────────────────────────────────────────────────────────────

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-line2 rounded-xl overflow-hidden">
      <div className="px-5 py-3.5 border-b border-line2 bg-ink2/40">
        <span className="font-mono text-[11px] uppercase tracking-wider text-cream2">{title}</span>
      </div>
      <div className="px-5 py-5">{children}</div>
    </div>
  )
}

function Input({
  type = 'text',
  value,
  onChange,
  placeholder,
}: {
  type?: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full h-11 px-3 rounded-lg border border-line2 bg-ink text-cream text-sm placeholder:text-mute focus:outline-none focus:border-amber transition"
    />
  )
}

// ── Change Password ────────────────────────────────────────────────────────────

function ChangePassword() {
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [saving, setSaving] = useState(false)
  const [success, setSuccess] = useState(false)
  const [error, setError] = useState('')

  function set(k: keyof typeof form, v: string) {
    setForm((f) => ({ ...f, [k]: v }))
    setError('')
    setSuccess(false)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!form.current || !form.next || !form.confirm) {
      setError('All fields are required.')
      return
    }
    if (form.next.length < 8) {
      setError('New password must be at least 8 characters.')
      return
    }
    if (form.next !== form.confirm) {
      setError('Passwords do not match.')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.post('/auth/change-password', {
        current_password: form.current,
        new_password: form.next,
      })
      setSuccess(true)
      setForm({ current: '', next: '', confirm: '' })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to change password')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">
          Current Password
        </label>
        <Input type="password" value={form.current} onChange={(v) => set('current', v)} placeholder="••••••••" />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">
            New Password
          </label>
          <Input type="password" value={form.next} onChange={(v) => set('next', v)} placeholder="Min 8 characters" />
        </div>
        <div className="space-y-1.5">
          <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">
            Confirm New Password
          </label>
          <Input type="password" value={form.confirm} onChange={(v) => set('confirm', v)} placeholder="Repeat new password" />
        </div>
      </div>

      {error && (
        <p className="font-mono text-[11px] text-red-soft">{error}</p>
      )}

      <div className="flex items-center gap-3 pt-1">
        <button
          type="submit"
          disabled={saving}
          className="h-9 px-5 rounded-lg bg-amber text-ink text-sm font-semibold hover:bg-amber2 disabled:opacity-50 transition"
        >
          {saving ? 'Saving…' : 'Update Password'}
        </button>
        {success && (
          <span className="font-mono text-xs text-green flex items-center gap-1.5">
            <svg viewBox="0 0 24 24" className="w-3.5 h-3.5" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M20 6L9 17l-5-5" />
            </svg>
            Password updated
          </span>
        )}
      </div>
    </form>
  )
}

// ── Export Data ────────────────────────────────────────────────────────────────

function ExportData() {
  const [loading, setLoading] = useState(false)

  async function handleExport() {
    setLoading(true)
    try {
      const profile = await api.get<unknown>('/profile')
      const blob = new Blob([JSON.stringify(profile, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `jobcrawler-profile-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch { /* ignore */ }
    setLoading(false)
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-cream2">
        Download your profile data as a JSON file. Includes all fields, skills, and preferences.
      </p>
      <button
        onClick={handleExport}
        disabled={loading}
        className="h-9 px-5 rounded-lg border border-line2 text-cream2 text-sm hover:border-cream2 hover:text-cream disabled:opacity-50 transition flex items-center gap-2"
      >
        <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="7 10 12 15 17 10" />
          <line x1="12" y1="15" x2="12" y2="3" />
        </svg>
        {loading ? 'Exporting…' : 'Export Profile JSON'}
      </button>
    </div>
  )
}

// ── Delete Account ─────────────────────────────────────────────────────────────

function DeleteAccount() {
  const { logout } = useAuth()
  const [showModal, setShowModal] = useState(false)
  const [confirm, setConfirm] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState('')

  async function handleDelete() {
    if (confirm !== 'DELETE') {
      setError('Type DELETE to confirm.')
      return
    }
    setDeleting(true)
    setError('')
    try {
      await api.del('/auth/me')
      logout()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete account')
      setDeleting(false)
    }
  }

  return (
    <>
      <div className="space-y-3">
        <p className="text-sm text-cream2">
          Permanently delete your account and all associated data. This action cannot be undone.
        </p>
        <button
          onClick={() => setShowModal(true)}
          className="h-9 px-5 rounded-lg border border-red-soft/30 text-red-soft text-sm hover:bg-red-soft/10 transition"
        >
          Delete Account
        </button>
      </div>

      {/* Confirmation modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/60" onClick={() => setShowModal(false)} />
          <div className="relative z-10 w-full max-w-md border border-line2 rounded-xl bg-ink p-6 space-y-4">
            <h3 className="font-serif text-xl text-cream">Delete account?</h3>
            <p className="text-sm text-cream2">
              This will permanently delete your profile, all applications, and billing history.
              This cannot be undone.
            </p>
            <div className="space-y-1.5">
              <label className="font-mono text-[11px] uppercase tracking-wider text-cream2">
                Type DELETE to confirm
              </label>
              <input
                type="text"
                value={confirm}
                onChange={(e) => { setConfirm(e.target.value); setError('') }}
                placeholder="DELETE"
                className="w-full h-11 px-3 rounded-lg border border-line2 bg-ink2 text-cream text-sm placeholder:text-mute focus:outline-none focus:border-red-soft/60 transition"
              />
            </div>
            {error && <p className="font-mono text-[11px] text-red-soft">{error}</p>}
            <div className="flex gap-3 pt-1">
              <button
                onClick={handleDelete}
                disabled={deleting}
                className="h-9 px-5 rounded-lg bg-red-soft/90 text-ink text-sm font-semibold hover:bg-red-soft disabled:opacity-50 transition"
              >
                {deleting ? 'Deleting…' : 'Delete Forever'}
              </button>
              <button
                onClick={() => { setShowModal(false); setConfirm(''); setError('') }}
                className="h-9 px-4 rounded-lg border border-line2 text-cream2 text-sm hover:text-cream transition"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ── Extension Status ───────────────────────────────────────────────────────────

function ExtensionStatus() {
  return (
    <div className="flex items-start gap-4">
      <div className="w-8 h-8 rounded-lg border border-line2 bg-ink2/40 flex items-center justify-center shrink-0 mt-0.5">
        <svg viewBox="0 0 24 24" className="w-4 h-4 text-mute" fill="none" stroke="currentColor" strokeWidth="1.7">
          <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2V9M9 21H5a2 2 0 0 1-2-2V9m0 0h18" />
        </svg>
      </div>
      <div>
        <p className="text-sm text-cream font-medium">Chrome Extension</p>
        <p className="text-xs text-mute mt-0.5">
          Extension status is visible in the extension popup. Install from the{' '}
          <span className="text-amber">Chrome Web Store</span> or load unpacked from{' '}
          <span className="font-mono text-cream2">extension/dist/</span>.
        </p>
        <div className="mt-3 inline-flex items-center gap-2 h-7 px-3 rounded-full border border-line2 bg-ink2/40">
          <span className="w-1.5 h-1.5 rounded-full bg-mute" />
          <span className="font-mono text-[10px] text-mute">Status detection coming soon</span>
        </div>
      </div>
    </div>
  )
}

// ── Main ───────────────────────────────────────────────────────────────────────

export function Settings() {
  return (
    <div className="p-8 max-w-2xl">
      <div className="mb-6">
        <h1 className="font-serif text-[2rem] text-cream">Settings</h1>
        <p className="text-cream2 text-sm mt-1">Account and security settings.</p>
      </div>

      <div className="space-y-4">
        <SectionCard title="Change Password">
          <ChangePassword />
        </SectionCard>

        <SectionCard title="Export Data">
          <ExportData />
        </SectionCard>

        <SectionCard title="Extension Connection">
          <ExtensionStatus />
        </SectionCard>

        <SectionCard title="Danger Zone">
          <DeleteAccount />
        </SectionCard>
      </div>
    </div>
  )
}
