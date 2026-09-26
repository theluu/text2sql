import type { ReactNode } from 'react'

/** A stat tile: the number is the design; the label says what it is. */
export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: 'ok' | 'warn' | 'block' }) {
  const color = tone === 'ok' ? 'text-ok' : tone === 'warn' ? 'text-warn' : tone === 'block' ? 'text-block' : 'text-ink'
  return (
    <div className="border-l border-rule px-4 py-1 first:border-l-0 first:pl-0">
      <p className="text-xs text-ink-2">{label}</p>
      <p className={`mt-1 font-display text-3xl font-semibold tabular-nums tracking-tight ${color}`}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-ink-3">{hint}</p>}
    </div>
  )
}

export function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`
}

/** Inline bar inside a table cell: magnitude plus the printed value, never color alone. */
export function MeterCell({ value }: { value: number | null }) {
  if (value === null) return <span className="text-ink-3">—</span>
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <span className="block h-full rounded-full bg-[var(--series-1)]" style={{ width: `${Math.max(2, value * 100)}%` }} />
      </span>
      <span className="font-mono text-xs tabular-nums">{pct(value, 0)}</span>
    </span>
  )
}
