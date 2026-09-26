import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatCompact, formatNumber } from '@/lib/format'
import type { ChartSpec, ResultSet } from './types'

const SERIES = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)']
const AXIS = { fontSize: 11, fill: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }

function records(result: ResultSet): Record<string, unknown>[] {
  return result.rows.map((row) => Object.fromEntries(result.columns.map((c, i) => [c, row[i]])))
}

/** Long → wide: one row per x, one key per series value (e.g. month × {online, offline}). */
export function pivot(result: ResultSet, x: string, series: string, y: string): { data: Record<string, unknown>[]; keys: string[] } {
  const xi = result.columns.indexOf(x)
  const si = result.columns.indexOf(series)
  const yi = result.columns.indexOf(y)
  const keys: string[] = []
  const byX = new Map<unknown, Record<string, unknown>>()
  for (const row of result.rows) {
    const key = String(row[si])
    if (!keys.includes(key)) keys.push(key)
    const entry = byX.get(row[xi]) ?? { [x]: row[xi] }
    entry[key] = row[yi]
    byX.set(row[xi], entry)
  }
  return { data: [...byX.values()], keys }
}

const legendText = (value: string) => <span style={{ color: 'var(--ink-2)' }}>{value}</span>

const tooltip = {
  contentStyle: {
    background: 'var(--surface)',
    border: '1px solid var(--rule)',
    borderRadius: 4,
    fontSize: 12,
    color: 'var(--ink)',
  },
  formatter: (value: unknown) => (typeof value === 'number' ? formatNumber(value) : String(value)),
}

export function ResultChart({ spec, result }: { spec: ChartSpec; result: ResultSet }) {
  if (spec.type === 'kpi') {
    const value = result.rows[0]?.[0]
    return (
      <p className="font-display text-5xl font-semibold tracking-tight tabular-nums">
        {typeof value === 'number' ? formatNumber(value) : String(value ?? '—')}
      </p>
    )
  }
  if (spec.type !== 'line' && spec.type !== 'bar') return null
  const wide = spec.series ? pivot(result, spec.x, spec.series, spec.y[0]) : null
  const data = wide ? wide.data : records(result)
  const keys = wide ? wide.keys : spec.y
  if (spec.type === 'line') {
    return (
      <div className="h-64" role="img" aria-label={`${spec.y.join(', ')} / ${spec.x}`}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--rule)" vertical={false} />
            <XAxis dataKey={spec.x} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--rule)' }} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={formatCompact} width={56} />
            <Tooltip {...tooltip} />
            {keys.length > 1 && <Legend formatter={legendText} itemSorter={null} iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12 }} />}
            {keys.map((key, i) => (
              <Line key={key} dataKey={key} name={key} stroke={SERIES[i]} strokeWidth={2} dot={data.length < 24 ? { r: 3, fill: SERIES[i], stroke: 'var(--surface)', strokeWidth: 1.5 } : false} isAnimationActive={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  }
  const horizontal = Boolean(spec.horizontal)
  const height = horizontal ? Math.max(160, data.length * 26 + 24) : 256
  return (
    <div style={{ height }} role="img" aria-label={`${spec.y.join(', ')} / ${spec.x}`}>
      <ResponsiveContainer>
        <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--rule)" horizontal={!horizontal} vertical={horizontal} />
          {horizontal ? (
            <>
              <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} tickFormatter={formatCompact} />
              <YAxis type="category" dataKey={spec.x} tick={AXIS} tickLine={false} axisLine={false} width={180} />
            </>
          ) : (
            <>
              <XAxis dataKey={spec.x} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--rule)' }} interval={0} angle={data.length > 8 ? -30 : 0} textAnchor={data.length > 8 ? 'end' : 'middle'} height={data.length > 8 ? 64 : 30} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={formatCompact} width={56} />
            </>
          )}
          <Tooltip {...tooltip} cursor={{ fill: 'var(--surface-2)' }} />
          {keys.length > 1 && <Legend formatter={legendText} itemSorter={null} iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12 }} />}
          {keys.map((key, i) => (
            <Bar key={key} dataKey={key} name={key} fill={SERIES[i]} stroke="var(--surface)" strokeWidth={keys.length > 1 ? 2 : 0} radius={[1, 1, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
