import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { StatsCard } from '../components/StatsCard'
import { useAuth } from '../auth/AuthContext'

// ── Types ──────────────────────────────────────────────────────────────────────

interface DiscoveryStats {
  applied_today: number
  applied_week: number
  queue_approved: number
  scored_needs_review: number
}

interface AppItem {
  id: string
  company: string | null
  title: string | null
  fit_score: number | null
  status: string
  applied_at: string | null
  updated_at: string
}

interface AppListResp {
  total: number
  items: AppItem[]
}

interface Completeness {
  complete: boolean
  missing_fields: string[]
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  applied: 'text-green bg-green/10 border-green/20',
  approved: 'text-indigo-300 bg-indigo-500/10 border-indigo-500/20',
  applying: 'text-amber bg-amber/10 border-amber/20',
  scored: 'text-blue-300 bg-blue-500/10 border-blue-500/20',
  interview: 'text-purple-300 bg-purple-500/10 border-purple-500/20',
  offer: 'text-green bg-green/20 border-green/30',
  rejected: 'text-red-soft bg-red-soft/10 border-red-soft/20',
}

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center h-5 px-2 rounded-full border font-mono text-[10px] font-medium ${
        STATUS_COLOR[status] ?? 'text-mute bg-line2 border-line2'
      }`}
    >
      {status}
    </span>
  )
}

function ScoreDot({ score }: { score: number | null }) {
  if (score === null) return <span className="text-mute font-mono text-xs">—</span>
  const n = Math.round(score)
  const c = n >= 80 ? 'text-green' : n >= 60 ? 'text-amber' : 'text-red-soft'
  return <span className={`font-mono text-sm font-semibold ${c}`}>{n}</span>
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function greet(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

// ── Icons ──────────────────────────────────────────────────────────────────────

function IconSend() {
  return (
    <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function IconCalendar() {
  return (
    <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  )
}

function IconQueue() {
  return (
    <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
      <polyline points="9 11 12 14 22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  )
}

function IconStar() {
  return (
    <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8">
      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
    </svg>
  )
}

// ── Component ──────────────────────────────────────────────────────────────────

export function Dashboard() {
  const { user } = useAuth()
  const { data: stats, loading: statsLoading } = useApi<DiscoveryStats>('/discovery/stats')
  const { data: recent, loading: recentLoading } = useApi<AppListResp>('/jobs?limit=5')
  const { data: completeness } = useApi<Completeness>('/profile/completeness')

  const name = user?.email?.split('@')[0] ?? 'there'

  return (
    <div className="px-6 py-8 max-w-5xl mx-auto">
      {/* Greeting */}
      <div className="mb-8">
        <h2 className="font-serif text-[1.85rem] text-cream">{greet()}, {name}.</h2>
        <p className="text-cream2 text-sm mt-1">Here's what's happening with your job search.</p>
      </div>

      {/* Profile completeness banner */}
      {completeness && !completeness.complete && (
        <div className="mb-6 flex items-start justify-between gap-4 rounded-xl border border-amber/30 bg-amber/5 px-5 py-4">
          <div>
            <p className="text-sm font-medium text-cream">Complete your profile</p>
            <p className="text-xs text-cream2 mt-1">
              Missing:{' '}
              <span className="font-mono text-amber/90">
                {completeness.missing_fields.join(', ')}
              </span>
            </p>
          </div>
          <Link
            to="/onboarding"
            className="shrink-0 inline-flex items-center h-8 px-4 rounded-lg bg-amber text-ink text-xs font-semibold hover:bg-amber2 transition"
          >
            Fix now →
          </Link>
        </div>
      )}

      {/* Stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatsCard
          label="Applied Today"
          value={stats?.applied_today ?? 0}
          icon={<IconSend />}
          positive={(stats?.applied_today ?? 0) > 0}
          loading={statsLoading}
        />
        <StatsCard
          label="Applied This Week"
          value={stats?.applied_week ?? 0}
          icon={<IconCalendar />}
          loading={statsLoading}
        />
        <StatsCard
          label="Queue Ready"
          value={stats?.queue_approved ?? 0}
          icon={<IconQueue />}
          accent={(stats?.queue_approved ?? 0) > 0}
          trend={(stats?.queue_approved ?? 0) > 0 ? 'waiting to apply' : undefined}
          loading={statsLoading}
        />
        <StatsCard
          label="Jobs Scored"
          value={stats?.scored_needs_review ?? 0}
          icon={<IconStar />}
          accent={(stats?.scored_needs_review ?? 0) > 0}
          trend={(stats?.scored_needs_review ?? 0) > 0 ? 'needs your review' : undefined}
          loading={statsLoading}
        />
      </div>

      {/* Quick actions */}
      <div className="mb-8">
        <h3 className="font-mono text-[11px] uppercase tracking-wider text-mute mb-3">
          Quick Actions
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <QuickAction
            to="/review"
            label="Review Queue"
            desc="Approve or reject scored jobs."
            badge={(stats?.scored_needs_review ?? 0) > 0 ? stats!.scored_needs_review : undefined}
            primary
          />
          <QuickAction
            to="/applications"
            label="View Applications"
            desc="Full history of all applications."
          />
          <QuickAction
            to="/profile"
            label="Edit Profile"
            desc="Update skills, salary, preferences."
          />
        </div>
      </div>

      {/* Recent applications */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-mono text-[11px] uppercase tracking-wider text-mute">
            Recent Applications
          </h3>
          <Link to="/applications" className="text-xs text-indigo-400 hover:underline underline-offset-4">
            View all →
          </Link>
        </div>

        <div className="border border-line2 rounded-xl overflow-hidden">
          {/* Header */}
          <div className="hidden sm:grid grid-cols-[1fr_130px_60px_90px_80px] gap-4 px-5 py-3 border-b border-line2 bg-ink2/40">
            {['Company / Title', 'Company', 'Score', 'Status', 'When'].map((h, i) => (
              <span key={i} className={`font-mono text-[10px] uppercase tracking-wider text-mute ${i === 0 ? '' : ''}`}>
                {i === 0 ? 'Job' : h}
              </span>
            ))}
          </div>

          {recentLoading ? (
            <div className="py-12 text-center font-mono text-xs text-mute animate-pulse">
              Loading…
            </div>
          ) : !recent?.items.length ? (
            <div className="py-12 text-center">
              <p className="text-cream2 text-sm">No applications yet.</p>
              <p className="text-mute text-xs mt-1">
                Install the Chrome extension and run a discovery session to get started.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-line2">
              {recent.items.map((app) => (
                <div
                  key={app.id}
                  className="grid grid-cols-[1fr_auto] sm:grid-cols-[1fr_130px_60px_90px_80px] gap-x-4 gap-y-1 px-5 py-3.5 items-center hover:bg-ink2/30 transition-colors"
                >
                  <div className="min-w-0">
                    <p className="text-sm text-cream truncate">{app.title ?? '—'}</p>
                    <p className="font-mono text-[11px] text-mute sm:hidden">{app.company ?? ''}</p>
                  </div>
                  <span className="hidden sm:block text-sm text-cream2 truncate">{app.company ?? '—'}</span>
                  <div className="hidden sm:flex"><ScoreDot score={app.fit_score} /></div>
                  <div className="hidden sm:flex"><StatusPill status={app.status} /></div>
                  <span className="hidden sm:block font-mono text-[11px] text-mute">
                    {timeAgo(app.applied_at ?? app.updated_at)}
                  </span>
                  {/* Mobile: status pill on right */}
                  <div className="sm:hidden flex items-center gap-2">
                    <StatusPill status={app.status} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ── QuickAction ────────────────────────────────────────────────────────────────

function QuickAction({
  to,
  label,
  desc,
  badge,
  primary,
}: {
  to: string
  label: string
  desc: string
  badge?: number
  primary?: boolean
}) {
  return (
    <Link
      to={to}
      className={`group flex items-center justify-between rounded-xl border px-4 py-4 transition-all ${
        primary
          ? 'border-indigo-500/25 bg-indigo-500/8 hover:bg-indigo-500/15'
          : 'border-line2 bg-ink2/30 hover:border-indigo-500/20 hover:bg-ink2/60'
      }`}
    >
      <div>
        <p className={`text-sm font-medium ${primary ? 'text-indigo-300' : 'text-cream'} group-hover:text-indigo-300 transition-colors`}>
          {label}
        </p>
        <p className="text-xs text-mute mt-0.5">{desc}</p>
      </div>
      <div className="flex items-center gap-2 pl-3">
        {badge !== undefined && (
          <span className="font-mono text-[11px] bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded-full border border-indigo-500/20">
            {badge}
          </span>
        )}
        <svg
          viewBox="0 0 24 24"
          className={`w-4 h-4 shrink-0 transition-colors ${primary ? 'text-indigo-400' : 'text-mute group-hover:text-indigo-400'}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
      </div>
    </Link>
  )
}
