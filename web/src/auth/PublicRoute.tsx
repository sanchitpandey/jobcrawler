import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext'
import type { ReactNode } from 'react'

export function PublicRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink">
        <div className="font-mono text-sm text-cream2">loading…</div>
      </div>
    )
  }

  if (user) return <Navigate to={user.is_verified ? '/dashboard' : '/verify-email'} replace />

  return <>{children}</>
}
