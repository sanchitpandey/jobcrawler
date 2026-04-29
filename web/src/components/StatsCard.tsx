import type { ReactNode } from 'react'

interface StatsCardProps {
  label: string
  value: number | string
  icon?: ReactNode
  /** e.g. "+12 this week" */
  trend?: string
  /** When true the number is coloured green */
  positive?: boolean
  /** Faint amber glow — use for actionable items like "queue ready" */
  accent?: boolean
  loading?: boolean
}

export function StatsCard({
  label,
  value,
  icon,
  trend,
  positive,
  accent,
  loading,
}: StatsCardProps) {
  const valueColor = positive
    ? 'text-green'
    : accent
      ? 'text-indigo-400'
      : 'text-cream'

  return (
    <div
      className={`relative overflow-hidden rounded-xl border p-5 flex flex-col gap-3 transition-colors ${
        accent
          ? 'border-indigo-500/20 bg-indigo-500/5'
          : 'border-line2 bg-ink2/50'
      }`}
    >
      {/* Icon + label row */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-[11px] uppercase tracking-wider text-mute">
          {label}
        </span>
        {icon && (
          <span className={`${accent ? 'text-indigo-400' : 'text-mute'}`}>
            {icon}
          </span>
        )}
      </div>

      {/* Value */}
      {loading ? (
        <div className="h-9 w-16 rounded-md bg-line2 animate-pulse" />
      ) : (
        <span className={`font-mono text-3xl font-semibold leading-none ${valueColor}`}>
          {value}
        </span>
      )}

      {/* Trend */}
      {trend && !loading && (
        <span className="font-mono text-[11px] text-mute">{trend}</span>
      )}

      {/* Accent decoration */}
      {accent && (
        <span className="pointer-events-none absolute -top-4 -right-4 w-20 h-20 rounded-full bg-indigo-500/8 blur-2xl" />
      )}
    </div>
  )
}
