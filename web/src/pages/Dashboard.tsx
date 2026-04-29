import { useAuth } from '../auth/AuthContext'

export function Dashboard() {
  const { user, logout } = useAuth()
  return (
    <div className="min-h-screen bg-ink text-cream p-8">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <h1 className="font-serif text-4xl">Dashboard</h1>
          <button onClick={logout} className="font-mono text-xs text-cream2 hover:text-cream border border-line2 px-3 py-1.5 rounded-md">
            sign out
          </button>
        </div>
        <p className="text-cream2 font-mono text-sm">Signed in as {user?.email} · tier: {user?.tier}</p>
        <p className="mt-8 text-cream2">Dashboard coming soon.</p>
      </div>
    </div>
  )
}
