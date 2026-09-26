import { AlertTriangle, CheckCircle2, CircleDashed } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Kpi, pct } from '@/features/eval/Kpi'
import { formatMs, formatUsd } from '@/lib/format'
import { type ProviderHealth, useOps } from './api'
import { ChartCard, Lines, SingleBars, StackedBars } from './charts'

const RANGES = [7, 14, 30]

function CircuitBadge({ state }: { state: ProviderHealth['circuit'] }) {
  const { t } = useTranslation()
  if (!state) return <span className="text-ink-3">—</span>
  const [Icon, tone] = state === 'closed' ? [CheckCircle2, 'text-ok'] : state === 'open' ? [AlertTriangle, 'text-block'] : [CircleDashed, 'text-warn']
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${tone}`}>
      <Icon size={13} aria-hidden /> {t(`ops.circuit.${state}`)}
    </span>
  )
}

export function OpsPage() {
  const { t } = useTranslation()
  const [days, setDays] = useState(14)
  const { data, isError, refetch } = useOps(days)
  const series = (keys: string[], colors: string[]) => keys.map((key, i) => ({ key, label: t(`ops.series.${key}`), color: colors[i] }))
  const decisionSeries = series(['auto', 'review', 'reject'], ['var(--chart-auto)', 'var(--chart-review)', 'var(--chart-reject)'])
  const resilienceSeries = series(['failover', 'fallback'], ['var(--series-1)', 'var(--series-2)'])
  const totals = data?.totals
  const maxGuardrail = Math.max(1, ...(data?.guardrails.map((g) => g.count) ?? [1]))

  return (
    <section className="px-8 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">{t('ops.title')}</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink-2">{t('ops.subtitle', { days })}</p>
        </div>
        <div role="group" aria-label={t('ops.range')} className="flex rounded-[4px] border border-rule p-0.5 text-xs">
          {RANGES.map((value) => (
            <button key={value} type="button" aria-pressed={days === value} onClick={() => setDays(value)}
              className={`rounded-[3px] px-2.5 py-1 ${days === value ? 'bg-ink text-paper' : 'text-ink-2 hover:text-ink'}`}>
              {t('ops.days', { count: value })}
            </button>
          ))}
        </div>
      </header>

      {isError && (
        <p role="alert" className="mt-6 text-sm text-block">
          {t('review.errors.load')}{' '}
          <button type="button" onClick={() => void refetch()} className="text-accent hover:underline">{t('common.retry')}</button>
        </p>
      )}

      {totals && (
        <div className="mt-8 grid grid-cols-2 gap-y-6 md:grid-cols-4 xl:grid-cols-8">
          <Kpi label={t('ops.kpi.questions')} value={totals.questions} />
          <Kpi label={t('ops.kpi.auto')} value={pct(totals.auto_rate, 0)} />
          <Kpi label={t('ops.kpi.pending')} value={totals.pending_reviews} tone={totals.pending_reviews ? 'warn' : undefined} />
          <Kpi label={t('ops.kpi.fallback')} value={pct(totals.fallback_rate, 0)} />
          <Kpi label={t('ops.kpi.failover')} value={pct(totals.failover_rate, 0)} />
          <Kpi label={t('ops.kpi.p95')} value={totals.latency_p95_ms === null ? '—' : formatMs(totals.latency_p95_ms)} />
          <Kpi label={t('ops.kpi.cost')} value={formatUsd(totals.cost_usd)} />
          <Kpi label={t('ops.kpi.agreement')} value={pct(totals.judge_human_agreement, 0)} />
        </div>
      )}

      {data && (
        <>
          <div className="mt-10 grid gap-6 xl:grid-cols-2">
            <ChartCard title={t('ops.decisions')} rows={data.decisions}
              columns={[{ key: 'day', label: t('ops.day') }, ...decisionSeries.map((s) => ({ key: s.key, label: s.label })), { key: 'failed', label: t('ops.series.failed') }]}>
              <StackedBars data={data.decisions} series={decisionSeries} />
            </ChartCard>
            <ChartCard title={t('ops.resilience')} rows={data.decisions}
              columns={[{ key: 'day', label: t('ops.day') }, ...resilienceSeries.map((s) => ({ key: s.key, label: s.label }))]}>
              <Lines data={data.decisions} series={resilienceSeries} />
            </ChartCard>
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[3fr_2fr]">
            <section className="rounded-[6px] border border-rule bg-surface p-4">
              <h2 className="text-sm font-medium">{t('ops.providers')}</h2>
              <table className="mt-3 w-full text-sm">
                <thead className="text-left text-xs text-ink-3">
                  <tr>
                    {(['name', 'status', 'circuit', 'calls', 'errors', 'latency'] as const).map((c) => (
                      <th key={c} className={`py-1 font-medium ${['calls', 'errors', 'latency'].includes(c) ? 'text-right' : ''}`}>{t(`ops.providerColumns.${c}`)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.providers.map((p) => (
                    <tr key={p.name} className="border-t border-rule/70">
                      <td className="py-2">
                        <span className="font-medium">{p.name}</span>
                        {p.model && <span className="block font-mono text-[11px] text-ink-3">{p.model}</span>}
                      </td>
                      <td className="py-2 text-xs">
                        {!p.configured ? <span className="text-ink-3">{t('ops.notConfigured')}</span>
                          : p.chaos ? <span className="font-medium text-warn">{t('ops.chaos')}</span>
                          : !p.in_chain ? <span className="text-ink-3">{t('ops.notInChain')}</span> : <span className="text-ink-2">✓</span>}
                      </td>
                      <td className="py-2"><CircuitBadge state={p.circuit} /></td>
                      <td className="py-2 text-right font-mono tabular-nums">{p.calls}</td>
                      <td className="py-2 text-right font-mono tabular-nums">{pct(p.error_rate, 0)}</td>
                      <td className="py-2 text-right font-mono tabular-nums text-ink-2">{p.avg_latency_ms === null ? '—' : formatMs(p.avg_latency_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
            <section className="rounded-[6px] border border-rule bg-surface p-4">
              <h2 className="text-sm font-medium">{t('ops.guardrails')}</h2>
              {data.guardrails.length === 0 ? <p className="py-8 text-center text-sm text-ink-3">{t('ops.empty')}</p> : (
                <ul className="mt-3 space-y-2 text-sm">
                  {data.guardrails.map((g) => (
                    <li key={`${g.layer}-${g.code}`} className="grid grid-cols-[1fr_auto] items-center gap-2">
                      <span className="truncate"><span className="font-mono text-[11px] text-ink-3">{g.layer}</span> {g.code}</span>
                      <MeterCellCount value={g.count} max={maxGuardrail} />
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div className="mt-6">
            <ChartCard title={t('ops.costs')} rows={data.costs}
              columns={[{ key: 'day', label: t('ops.day') }, { key: 'cost_usd', label: 'USD' }, { key: 'calls', label: t('ops.providerColumns.calls') }, { key: 'tokens', label: 'tokens' }]}>
              <SingleBars data={data.costs} dataKey="cost_usd" label="USD" format={(v) => formatUsd(v)} />
            </ChartCard>
          </div>
        </>
      )}
    </section>
  )
}

function MeterCellCount({ value, max }: { value: number; max: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-1.5 w-28 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <span className="block h-full rounded-full bg-[var(--series-1)]" style={{ width: `${(value / max) * 100}%` }} />
      </span>
      <span className="w-8 text-right font-mono text-xs tabular-nums">{value}</span>
    </span>
  )
}

