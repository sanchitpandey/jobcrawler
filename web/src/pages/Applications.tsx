import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import { ApplicationRow, type AppRowItem } from '../components/ApplicationRow'

type AppItem = AppRowItem

interface ListResp {
  total: number
  items: AppItem[]
}

const STATUS_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'applied', label: 'Applied' },
  { value: 'approved', label: 'Approved' },
  { value: 'scored', label: 'Scored' },
  { value: 'applying', label: 'Applying' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'interview', label: 'Interview' },
  { value: 'offer', label: 'Offer' },
]

const PAGE_SIZE = 20

export function Applications() {
  const [items, setItems] = useState<AppItem[]>([])
  const [total, setTotal] = useState(0)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchApps = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = new URLSearchParams()
      if (statusFilter) params.set('status', statusFilter)
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(page * PAGE_SIZE))
      const data = await api.get<ListResp>(`/jobs?${params}`)
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load applications')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, page])

  useEffect(() => {
    setPage(0)
  }, [statusFilter])

  useEffect(() => {
    fetchApps()
  }, [fetchApps])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="p-8 max-w-6xl">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-serif text-[2rem] text-cream">Applications</h1>
          <p className="text-cream2 text-sm mt-1">
            {total > 0 ? `${total} total applications` : 'No applications yet'}
          </p>
        </div>
      </div>

      {/* Filters */}
      <div className="mb-5 flex items-center gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-9 px-3 rounded-lg border border-line2 bg-ink text-cream text-sm focus:outline-none focus:border-amber transition appearance-none"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value} className="bg-ink">
              {o.label}
            </option>
          ))}
        </select>
        <span className="font-mono text-[11px] text-mute">{total} results</span>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="border border-line2 rounded-xl overflow-hidden">
        {/* Table header */}
        <div className="grid grid-cols-[1fr_140px_60px_90px_80px] gap-4 px-5 py-3 border-b border-line2 bg-ink2/40">
          {['Job', 'Company', 'Score', 'Status', 'When'].map((h) => (
            <span key={h} className="font-mono text-[10px] uppercase tracking-wider text-mute">
              {h}
            </span>
          ))}
        </div>

        {loading ? (
          <div className="py-16 text-center font-mono text-sm text-mute animate-pulse">
            Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="py-16 text-center">
            <p className="text-cream2 text-sm">No applications found.</p>
            <p className="text-mute text-xs mt-1">
              Install the Chrome extension and start a discovery session to find jobs.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-line2">
            {items.map((app) => (
              <ApplicationRow key={app.id} app={app} />
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-5 flex items-center justify-between">
          <span className="font-mono text-xs text-mute">
            Page {page + 1} of {totalPages}
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="h-8 px-3 rounded-lg border border-line2 text-xs text-cream2 disabled:opacity-30 hover:border-cream2 transition"
            >
              ← Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="h-8 px-3 rounded-lg border border-line2 text-xs text-cream2 disabled:opacity-30 hover:border-cream2 transition"
            >
              Next →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
