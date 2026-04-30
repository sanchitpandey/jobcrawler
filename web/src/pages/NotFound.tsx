import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function NotFound() {
  const { user } = useAuth()
  const { pathname } = useLocation()

  return (
    <div className="min-h-screen bg-ink flex items-center justify-center px-4">
      <div className="text-center space-y-6 max-w-sm">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-xl border border-line2 bg-ink2/60">
          <span className="font-mono text-2xl text-mute">?</span>
        </div>

        <div className="space-y-2">
          <h1 className="font-serif text-4xl text-cream">404</h1>
          <p className="text-cream2 text-sm">
            <span className="font-mono text-amber">{pathname}</span> doesn't exist.
          </p>
        </div>

        <Link
          to={user ? '/dashboard' : '/'}
          className="inline-flex h-10 px-6 rounded-lg bg-amber text-ink text-sm font-semibold hover:bg-amber2 transition items-center"
        >
          {user ? '← Back to dashboard' : '← Back to home'}
        </Link>
      </div>
    </div>
  )
}
