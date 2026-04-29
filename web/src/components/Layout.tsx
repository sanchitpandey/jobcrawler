import { useState, useEffect } from 'react'
import { Link, useLocation, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

// ── Icons ──────────────────────────────────────────────────────────────────────

function Icon({ d, className }: { d: string | string[]; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className ?? 'w-[18px] h-[18px]'}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {Array.isArray(d) ? d.map((p, i) => <path key={i} d={p} />) : <path d={d} />}
    </svg>
  )
}

// ── Nav config ─────────────────────────────────────────────────────────────────

const NAV = [
  {
    path: '/dashboard',
    label: 'Dashboard',
    icon: (
      <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    ),
  },
  {
    path: '/applications',
    label: 'Applications',
    icon: (
      <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="9" y1="13" x2="15" y2="13" />
        <line x1="9" y1="17" x2="13" y2="17" />
      </svg>
    ),
  },
  {
    path: '/review',
    label: 'Review Queue',
    icon: (
      <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
        <polyline points="9 11 12 14 22 4" />
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
      </svg>
    ),
  },
  {
    path: '/profile',
    label: 'Profile',
    icon: (
      <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    ),
  },
  {
    path: '/billing',
    label: 'Billing',
    icon: (
      <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
        <line x1="1" y1="10" x2="23" y2="10" />
      </svg>
    ),
  },
  {
    path: '/settings',
    label: 'Settings',
    icon: (
      <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
  },
]

const PAGE_TITLE: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/applications': 'Applications',
  '/review': 'Review Queue',
  '/profile': 'Profile',
  '/billing': 'Billing',
  '/settings': 'Settings',
}

// ── Sidebar ────────────────────────────────────────────────────────────────────

function Sidebar({ onClose }: { onClose?: () => void }) {
  const { pathname } = useLocation()
  const { user, logout } = useAuth()

  return (
    <aside className="w-[250px] h-full bg-ink border-r border-line2 flex flex-col">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-line2 flex items-center justify-between">
        <Link to="/" onClick={onClose} className="inline-flex items-center gap-2.5">
          <span className="relative w-7 h-7 inline-flex items-center justify-center shrink-0">
            <span className="absolute inset-0 rounded-lg border border-line2" />
            <svg viewBox="0 0 24 24" className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.7">
              <circle cx="12" cy="12" r="3.2" stroke="#FF8A1F" />
              <path d="M12 8.8V4M12 15.2V20M8.8 12H4M15.2 12H20M9.7 9.7L6.3 6.3M14.3 9.7L17.7 6.3M9.7 14.3L6.3 17.7M14.3 14.3L17.7 17.7" stroke="#EDE6D6" />
            </svg>
          </span>
          <span className="font-semibold tracking-tight text-[15px] text-cream">JobCrawler</span>
        </Link>
        {/* Mobile close button */}
        {onClose && (
          <button
            onClick={onClose}
            className="md:hidden p-1 text-mute hover:text-cream transition-colors"
            aria-label="Close menu"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        )}
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {NAV.map(({ path, label, icon }) => {
          const active = pathname === path
          return (
            <Link
              key={path}
              to={path}
              onClick={onClose}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13.5px] font-medium transition-all ${
                active
                  ? 'bg-indigo-600/20 text-indigo-300 border border-indigo-500/25 shadow-sm'
                  : 'text-cream2 hover:text-cream hover:bg-ink2'
              }`}
            >
              <span className={active ? 'text-indigo-400' : 'text-mute'}>{icon}</span>
              {label}
            </Link>
          )
        })}
      </nav>

      {/* User footer */}
      <div className="px-3 py-3 border-t border-line2">
        <div className="px-3 py-2.5 rounded-lg bg-ink2/60 mb-1">
          <p className="text-[12px] text-cream font-medium truncate">{user?.email}</p>
          <span
            className={`mt-1 inline-block font-mono text-[9px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${
              user?.tier === 'paid'
                ? 'bg-green/15 text-green border-green/20'
                : 'bg-line2 text-mute border-line2'
            }`}
          >
            {user?.tier ?? 'free'}
          </span>
        </div>
        <button
          onClick={() => { onClose?.(); logout() }}
          className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] text-mute hover:text-cream2 hover:bg-ink2 transition-colors"
        >
          <Icon d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
          Sign out
        </button>
      </div>
    </aside>
  )
}

// ── Layout ─────────────────────────────────────────────────────────────────────

export function Layout() {
  const { pathname } = useLocation()
  const [mobileOpen, setMobileOpen] = useState(false)

  // Close sidebar on navigation on mobile
  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  // Trap scroll when mobile sidebar is open
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [mobileOpen])

  const pageTitle = PAGE_TITLE[pathname] ?? ''

  return (
    <div className="min-h-screen bg-ink flex">
      {/* ── Desktop sidebar (always visible on md+) ─────────────────────────── */}
      <div className="hidden md:block shrink-0 w-[250px] fixed inset-y-0 left-0 z-30">
        <Sidebar />
      </div>

      {/* ── Mobile sidebar + backdrop ────────────────────────────────────────── */}
      {mobileOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
            onClick={() => setMobileOpen(false)}
          />
          {/* Drawer */}
          <div className="fixed inset-y-0 left-0 z-50 md:hidden">
            <Sidebar onClose={() => setMobileOpen(false)} />
          </div>
        </>
      )}

      {/* ── Main area ────────────────────────────────────────────────────────── */}
      <div className="flex-1 md:ml-[250px] flex flex-col min-h-screen">
        {/* Top bar */}
        <header className="sticky top-0 z-20 flex items-center gap-4 px-6 h-14 border-b border-line2 bg-ink/80 backdrop-blur-sm">
          {/* Hamburger (mobile only) */}
          <button
            onClick={() => setMobileOpen(true)}
            className="md:hidden p-1.5 rounded-lg text-mute hover:text-cream hover:bg-ink2 transition-colors"
            aria-label="Open menu"
          >
            <svg viewBox="0 0 24 24" className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>

          {/* Page title */}
          {pageTitle && (
            <h1 className="text-[14px] font-semibold text-cream tracking-tight">{pageTitle}</h1>
          )}
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
