import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatCompact, formatNumber } from '@/lib/format'
import type { ChartSpec, ResultSet } from './types'

const SERIES = ['var(--accent)', 'var(--ok)', 'var(--warn)']
const AXIS = { fontSize: 11, fill: 'var(--ink-3)', fontFamily: 'var(--font-mono)' }

function records(result: ResultSet): Record<string, unknown>[] {
  return result.rows.map((row) => Object.fromEntries(result.columns.map((c, i) => [c, row[i]])))
}

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
  const data = records(result)
  if (spec.type === 'line') {
    return (
      <div className="h-64" role="img" aria-label={`${spec.y.join(', ')} / ${spec.x}`}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--rule)" vertical={false} />
            <XAxis dataKey={spec.x} tick={AXIS} tickLine={false} axisLine={{ stroke: 'var(--rule)' }} />
            <YAxis tick={AXIS} tickLine={false} axisLine={false} tickFormatter={formatCompact} width={56} />
            <Tooltip {...tooltip} />
            {spec.y.map((key, i) => (
              <Line key={key} dataKey={key} stroke={SERIES[i]} strokeWidth={2} dot={data.length < 24} isAnimationActive={false} />
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
          {spec.y.map((key, i) => (
            <Bar key={key} dataKey={key} fill={SERIES[i]} radius={[1, 1, 0, 0]} isAnimationActive={false} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
