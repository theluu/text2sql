import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatNumber } from '@/lib/format'

const AXIS = { fontSize: 11, fill: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }
const TOOLTIP = {
  contentStyle: { background: 'var(--surface)', border: '1px solid var(--rule)', borderRadius: 4, fontSize: 12, color: 'var(--ink)' },
  labelStyle: { color: 'var(--ink-2)' },
}
// Legend text wears ink, not the series color; keep series in their declared order.
const legendText = (value: string) => <span style={{ color: 'var(--ink-2)' }}>{value}</span>
const LEGEND = {
  wrapperStyle: { fontSize: 12 },
  iconType: 'square' as const,
  iconSize: 10,
  formatter: legendText,
  itemSorter: null,
}

export interface Series {
  key: string
  label: string
  color: string
}

const shortDay = (iso: string) => iso.slice(5).replace('-', '/')

/** A chart card: title, the plot, and a table view of the same numbers (never color alone). */
export function ChartCard({ title, children, rows, columns }: { title: string; children: ReactNode; rows: Record<string, unknown>[]; columns: { key: string; label: string }[] }) {
  const { t } = useTranslation()
  return (
    <figure className="rounded-[6px] border border-rule bg-surface p-4">
      <figcaption className="text-sm font-medium text-ink">{title}</figcaption>
      {rows.length === 0 ? <p className="py-10 text-center text-sm text-ink-3">{t('ops.empty')}</p> : <div className="mt-3">{children}</div>}
      {rows.length > 0 && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer text-ink-3 hover:text-ink">{t('ops.showTable')}</summary>
          <table className="mt-2 w-full">
            <thead className="text-left text-ink-3">
              <tr>{columns.map((c) => <th key={c.key} className="py-1 font-medium">{c.label}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i} className="border-t border-rule/60">
                  {columns.map((c) => (
                    <td key={c.key} className="py-1 font-mono tabular-nums">{typeof row[c.key] === 'number' ? formatNumber(row[c.key] as number, 4) : String(row[c.key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </figure>
  )
}

export function StackedBars({ data, series }: { data: Record<string, unknown>[]; series: Series[] }) {
  return (
    <div className="h-60">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis dataKey="day" tickFormatter={shortDay} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--rule)' }} />
          <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} width={32} />
          <Tooltip {...TOOLTIP} cursor={{ fill: 'var(--surface-2)' }} />
          <Legend {...LEGEND} />
          {series.map((s, i) => (
            <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} stroke="var(--surface)" strokeWidth={2}
              radius={i === series.length - 1 ? [4, 4, 0, 0] : 0} isAnimationActive={false} maxBarSize={36} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function Lines({ data, series }: { data: Record<string, unknown>[]; series: Series[] }) {
  return (
    <div className="h-60">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis dataKey="day" tickFormatter={shortDay} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--rule)' }} />
          <YAxis allowDecimals={false} tick={AXIS} tickLine={false} axisLine={false} width={32} />
          <Tooltip {...TOOLTIP} />
          <Legend {...LEGEND} />
          {series.map((s) => (
            <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} dot={{ r: 4, fill: s.color, strokeWidth: 2, stroke: 'var(--surface)' }} activeDot={{ r: 5, fill: s.color, stroke: 'var(--surface)', strokeWidth: 2 }} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

export function SingleBars({ data, dataKey, label, format }: { data: Record<string, unknown>[]; dataKey: string; label: string; format: (v: number) => string }) {
  return (
    <div className="h-60">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" vertical={false} />
          <XAxis dataKey="day" tickFormatter={shortDay} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--rule)' }} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} width={56} tickFormatter={format} />
          <Tooltip {...TOOLTIP} formatter={(v: unknown) => format(Number(v))} cursor={{ fill: 'var(--surface-2)' }} />
          <Bar dataKey={dataKey} name={label} fill="var(--series-1)" radius={[4, 4, 0, 0]} isAnimationActive={false} maxBarSize={36} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
