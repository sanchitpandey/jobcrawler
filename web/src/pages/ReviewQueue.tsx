import { useState, useEffect, useCallback } from 'react'
import { api } from '../api/client'
import { JobCard, type JobCardItem, type JobCardTab } from '../components/JobCard'

type AppItem = JobCardItem

interface ListResp {
  total: number
  items: AppItem[]
}

export function ReviewQueue() {
  const [tab, setTab] = useState<JobCardTab>('scored')
  const [items, setItems] = useState<AppItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const fetchItems = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.get<ListResp>(`/jobs?status=${tab}&limit=50`)
      setItems(data.items)
      setTotal(data.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load queue')
    } finally {
      setLoading(false)
    }
  }, [tab])

  useEffect(() => {
    fetchItems()
  }, [fetchItems])

  function removeItem(id: string) {
    setItems((prev) => prev.filter((a) => a.id !== id))
    setTotal((t) => Math.max(0, t - 1))
  }

  function moveToApproved(id: string) {
    setItems((prev) => prev.filter((a) => a.id !== id))
    setTotal((t) => Math.max(0, t - 1))
  }

  return (
    <div className="p-8 max-w-4xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="font-serif text-[2rem] text-cream">Review Queue</h1>
        <p className="text-cream2 text-sm mt-1">
          Approve jobs to queue them for auto-apply, or reject to skip them.
        </p>
      </div>

      {/* Tabs */}
      <div className="mb-6 flex items-center gap-1 border border-line2 rounded-xl p-1 w-fit">
        {([
          { id: 'scored', label: 'Needs Review' },
          { id: 'approved', label: 'Approved' },
        ] as { id: JobCardTab; label: string }[]).map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`h-8 px-4 rounded-lg text-sm font-medium transition-colors ${
              tab === id ? 'bg-amber/15 text-amber' : 'text-cream2 hover:text-cream'
            }`}
          >
            {label}
            {tab === id && total > 0 && (
              <span className="ml-2 font-mono text-[10px] bg-amber/20 px-1.5 py-0.5 rounded-full">
                {total}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 border border-red-soft/30 bg-red-soft/10 rounded-lg px-4 py-3 font-mono text-xs text-red-soft">
          {error}
        </div>
      )}

      {/* Bulk approve (scored tab only) */}
      {tab === 'scored' && items.length > 1 && (
        <div className="mb-4 flex items-center justify-between border border-line2 rounded-xl px-4 py-3 bg-ink2/30">
          <span className="text-sm text-cream2">{items.length} jobs scored and waiting for review</span>
          <button
            onClick={async () => {
              try {
                await api.post('/discovery/approve-batch', { min_score: 75 })
                await fetchItems()
              } catch (e) {
                setError(e instanceof Error ? e.message : 'Bulk approve failed')
              }
            }}
            className="h-8 px-4 rounded-lg bg-green/15 border border-green/25 text-green text-xs font-medium hover:bg-green/25 transition"
          >
            Approve all ≥ 75 →
          </button>
        </div>
      )}

      {/* Content */}
      {loading ? (
        <div className="py-20 text-center font-mono text-sm text-mute animate-pulse">
          Loading…
        </div>
      ) : items.length === 0 ? (
        <div className="py-20 text-center border border-line2 rounded-xl">
          <p className="text-cream2 text-sm">
            {tab === 'scored'
              ? 'No jobs waiting for review.'
              : 'No approved jobs in queue.'}
          </p>
          <p className="text-mute text-xs mt-1">
            {tab === 'scored'
              ? 'Run a discovery session from the Chrome extension to find and score jobs.'
              : 'Approve jobs from the "Needs Review" tab to queue them for auto-apply.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((app) => (
            <JobCard
              key={app.id}
              app={app}
              tab={tab}
              onApprove={moveToApproved}
              onReject={removeItem}
            />
          ))}
        </div>
      )}
    </div>
  )
}
