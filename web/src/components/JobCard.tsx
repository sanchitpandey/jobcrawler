import { useState } from 'react'
import { api } from '../api/client'

export interface JobCardItem {
  id: string
  company: string | null
  title: string | null
  location: string | null
  url: string | null
  fit_score: number | null
  verdict: string | null
  gaps: string[] | null
  status: string
  updated_at: string
}

export type JobCardTab = 'scored' | 'approved'

const VERDICT_LABEL: Record<string, string> = {
  strong_yes: 'Strong Yes',
  yes: 'Yes',
  maybe: 'Maybe',
  no: 'No',
}

const VERDICT_COLOR: Record<string, string> = {
  strong_yes: 'text-green border-green/30 bg-green/10',
  yes: 'text-green border-green/20 bg-green/8',
  maybe: 'text-amber border-amber/30 bg-amber/10',
  no: 'text-mute border-line2 bg-line2/30',
}

function ScoreRing({ score }: { score: number | null }) {
  if (score === null) return null
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : '#ff6b6b'
  const r = 18
  const circ = 2 * Math.PI * r
  const dash = (score / 100) * circ
  return (
    <svg width="48" height="48" viewBox="0 0 48 48" className="shrink-0">
      <circle cx="24" cy="24" r={r} fill="none" stroke="#1a1a2e" strokeWidth="4" />
      <circle
        cx="24"
        cy="24"
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="4"
        strokeDasharray={`${dash} ${circ - dash}`}
        strokeDashoffset={circ / 4}
        strokeLinecap="round"
        style={{ transition: 'stroke-dasharray 0.4s ease' }}
      />
      <text x="24" y="24" textAnchor="middle" dominantBaseline="central" fontSize="11" fontFamily="monospace" fill={color} fontWeight="600">
        {Math.round(score)}
      </text>
    </svg>
  )
}

export function JobCard({
  app,
  tab,
  onApprove,
  onReject,
}: {
  app: JobCardItem
  tab: JobCardTab
  onApprove: (id: string) => void
  onReject: (id: string) => void
}) {
  const [busy, setBusy] = useState(false)

  async function act(action: 'approve' | 'reject') {
    setBusy(true)
    try {
      if (action === 'approve') {
        await api.patch(`/discovery/${app.id}/status`, { status: 'approved' })
        onApprove(app.id)
      } else {
        await api.patch(`/discovery/${app.id}/status`, { status: 'rejected' })
        onReject(app.id)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border border-line2 rounded-xl p-5 hover:border-amber/20 transition-colors">
      <div className="flex items-start gap-4">
        <ScoreRing score={app.fit_score} />

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {app.url ? (
                <a
                  href={app.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[15px] font-medium text-cream hover:text-amber transition-colors truncate block"
                >
                  {app.title ?? 'Untitled'}
                </a>
              ) : (
                <p className="text-[15px] font-medium text-cream truncate">{app.title ?? 'Untitled'}</p>
              )}
              <p className="text-sm text-cream2 mt-0.5">
                {app.company ?? '—'}
                {app.location && <span className="text-mute"> · {app.location}</span>}
              </p>
            </div>
            {app.verdict && (
              <span
                className={`shrink-0 inline-flex items-center h-5 px-2 rounded-full border font-mono text-[10px] font-medium ${
                  VERDICT_COLOR[app.verdict] ?? 'text-mute border-line2'
                }`}
              >
                {VERDICT_LABEL[app.verdict] ?? app.verdict}
              </span>
            )}
          </div>

          {app.gaps && app.gaps.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {app.gaps.slice(0, 4).map((g, i) => (
                <span
                  key={i}
                  className="font-mono text-[10px] px-2 py-0.5 rounded-full border border-line2 text-cream2"
                >
                  {g}
                </span>
              ))}
              {app.gaps.length > 4 && (
                <span className="font-mono text-[10px] text-mute">+{app.gaps.length - 4} more</span>
              )}
            </div>
          )}
        </div>
      </div>

      {tab === 'scored' && (
        <div className="mt-4 flex items-center gap-2 border-t border-line2 pt-4">
          <button
            onClick={() => act('approve')}
            disabled={busy}
            className="h-8 px-4 rounded-lg bg-green/15 border border-green/25 text-green text-xs font-medium hover:bg-green/25 disabled:opacity-40 transition"
          >
            Approve →
          </button>
          <button
            onClick={() => act('reject')}
            disabled={busy}
            className="h-8 px-4 rounded-lg border border-line2 text-cream2 text-xs hover:border-red-soft/50 hover:text-red-soft disabled:opacity-40 transition"
          >
            Reject
          </button>
          {app.url && (
            <a
              href={app.url}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-auto h-8 px-3 rounded-lg border border-line2 text-mute text-xs hover:text-cream2 transition flex items-center gap-1"
            >
              View job ↗
            </a>
          )}
        </div>
      )}
      {tab === 'approved' && (
        <div className="mt-4 flex items-center gap-2 border-t border-line2 pt-4">
          <span className="font-mono text-[11px] text-green">Approved — will be applied to automatically</span>
          <button
            onClick={() => act('reject')}
            disabled={busy}
            className="ml-auto h-7 px-3 rounded-lg border border-line2 text-mute text-[11px] hover:border-red-soft/40 hover:text-red-soft disabled:opacity-40 transition"
          >
            Remove
          </button>
        </div>
      )}
    </div>
  )
}
