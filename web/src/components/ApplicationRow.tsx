export interface AppRowItem {
  id: string
  company: string | null
  title: string | null
  location: string | null
  url: string | null
  fit_score: number | null
  verdict: string | null
  status: string
  applied_at: string | null
  scored_at: string
  updated_at: string
}

const STATUS_STYLE: Record<string, string> = {
  applied:    'bg-green/15 text-green border-green/20',
  approved:   'bg-amber/15 text-amber border-amber/20',
  applying:   'bg-amber/15 text-amber border-amber/20',
  scored:     'bg-blue-400/15 text-blue-300 border-blue-400/20',
  interview:  'bg-purple-400/15 text-purple-300 border-purple-400/20',
  offer:      'bg-green/25 text-green border-green/30',
  rejected:   'bg-red-soft/15 text-red-soft border-red-soft/20',
  skipped:    'bg-line2 text-mute border-line2',
  failed:     'bg-red-soft/15 text-red-soft border-red-soft/20',
  discovered: 'bg-line2 text-mute border-line2',
  enriched:   'bg-line2 text-mute border-line2',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex items-center h-5 px-2 rounded-full border font-mono text-[10px] font-medium ${
        STATUS_STYLE[status] ?? 'bg-line2 text-mute border-line2'
      }`}
    >
      {status}
    </span>
  )
}

export function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-mute font-mono text-xs">—</span>
  const color = score >= 80 ? 'text-green' : score >= 60 ? 'text-amber' : 'text-red-soft'
  return <span className={`font-mono text-sm font-semibold ${color}`}>{score}</span>
}

export function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function ApplicationRow({ app }: { app: AppRowItem }) {
  const titleEl = app.url ? (
    <a
      href={app.url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-sm text-cream hover:text-amber transition-colors truncate block"
    >
      {app.title ?? '—'}
    </a>
  ) : (
    <span className="text-sm text-cream truncate block">{app.title ?? '—'}</span>
  )

  return (
    <>
      {/* Desktop row */}
      <div className="hidden sm:grid grid-cols-[1fr_140px_60px_90px_80px] gap-4 px-5 py-3.5 hover:bg-ink2/30 transition-colors items-center">
        <div className="min-w-0">
          {titleEl}
          {app.location && (
            <span className="font-mono text-[11px] text-mute">{app.location}</span>
          )}
        </div>
        <span className="text-sm text-cream2 truncate">{app.company ?? '—'}</span>
        <div className="flex items-center">
          <ScoreBadge score={app.fit_score !== null ? Math.round(app.fit_score) : null} />
        </div>
        <StatusBadge status={app.status} />
        <span className="font-mono text-[11px] text-mute">
          {timeAgo(app.applied_at ?? app.updated_at)}
        </span>
      </div>

      {/* Mobile card */}
      <div className="sm:hidden px-4 py-3.5 hover:bg-ink2/30 transition-colors flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          {titleEl}
          <p className="font-mono text-[11px] text-mute mt-0.5">
            {[app.company, app.location].filter(Boolean).join(' · ')}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <StatusBadge status={app.status} />
          <div className="flex items-center gap-2">
            <ScoreBadge score={app.fit_score !== null ? Math.round(app.fit_score) : null} />
            <span className="font-mono text-[10px] text-mute">{timeAgo(app.applied_at ?? app.updated_at)}</span>
          </div>
        </div>
      </div>
    </>
  )
}
