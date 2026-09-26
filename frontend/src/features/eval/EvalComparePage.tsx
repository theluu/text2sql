import { Link, useSearch } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatMs } from '@/lib/format'
import { type CompareEntry, type EvalSummary, useComparison } from './api'
import { modeLabel } from './EvalPage'
import { pct } from './Kpi'

const METRICS: { key: keyof EvalSummary; label: string; format: (v: number) => string; higherIsBetter: boolean }[] = [
  { key: 'ex', label: 'eval.kpi.ex', format: (v) => pct(v), higherIsBetter: true },
  { key: 'behavior_accuracy', label: 'eval.kpi.behavior', format: (v) => pct(v), higherIsBetter: true },
  { key: 'guardrail_recall', label: 'eval.kpi.guardrail', format: (v) => pct(v, 0), higherIsBetter: true },
  { key: 'esm', label: 'eval.kpi.esm', format: (v) => pct(v), higherIsBetter: true },
  { key: 'linking_recall', label: 'eval.kpi.linking', format: (v) => pct(v), higherIsBetter: true },
  { key: 'latency_p95_ms', label: 'eval.kpi.p95', format: (v) => formatMs(v), higherIsBetter: false },
  { key: 'fallback_rate', label: 'eval.kpi.fallback', format: (v) => pct(v, 0), higherIsBetter: false },
]

function CaseList({ title, entries, tone }: { title: string; entries: CompareEntry[]; tone: string }) {
  const { t } = useTranslation()
  return (
    <div>
      <h2 className={`text-sm font-medium ${tone}`}>{title}</h2>
      {entries.length === 0 ? (
        <p className="mt-2 text-sm text-ink-3">{t('eval.nothing')}</p>
      ) : (
        <ul className="mt-2 divide-y divide-rule/70 rounded-[6px] border border-rule bg-surface">
          {entries.map((e) => (
            <li key={e.key} className="px-3 py-2 text-sm">
              <span className="font-mono text-xs text-ink-3">{e.key}</span> {e.question}
              <span className="block text-xs text-ink-2">
                {t(`eval.behaviors.${e.before}`)} → {t(`eval.behaviors.${e.after}`)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function EvalComparePage() {
  const { t } = useTranslation()
  const { a, b } = useSearch({ from: '/_app/eval/compare' })
  const { data } = useComparison(a ?? '', b ?? '')
  if (!data) return <div className="p-8"><div className="h-6 w-1/3 animate-pulse rounded bg-surface-2" /></div>
  const label = (run: typeof data.a) => `${t(`eval.suites.${run.suite}`, run.suite)} · ${modeLabel(t, run.mode)} · ${run.git_sha?.slice(0, 7) ?? '—'}`

  return (
    <section className="px-8 py-8">
      <Link to="/eval" className="flex items-center gap-1 text-sm text-ink-2 hover:text-ink"><ArrowLeft size={14} /> {t('eval.back')}</Link>
      <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight">{t('eval.compare')}</h1>
      <p className="mt-1 text-sm text-ink-2">A: {label(data.a)}<br />B: {label(data.b)}</p>

      <h2 className="mt-8 text-sm font-medium text-ink-2">{t('eval.deltaTitle')}</h2>
      <table className="mt-2 w-full max-w-2xl text-sm">
        <thead className="text-left text-xs text-ink-3">
          <tr><th className="py-1 font-medium">{t('eval.metric')}</th><th className="py-1 text-right font-medium">A</th><th className="py-1 text-right font-medium">B</th><th className="py-1 text-right font-medium">Δ</th></tr>
        </thead>
        <tbody>
          {METRICS.map((m) => {
            const va = data.a.summary?.[m.key] as number | null | undefined
            const vb = data.b.summary?.[m.key] as number | null | undefined
            const delta = va !== null && va !== undefined && vb !== null && vb !== undefined ? vb - va : null
            const better = delta !== null && delta !== 0 && (delta > 0) === m.higherIsBetter
            return (
              <tr key={m.key} className="border-t border-rule/70">
                <td className="py-1.5">{t(m.label)}</td>
                <td className="py-1.5 text-right font-mono tabular-nums">{va === null || va === undefined ? '—' : m.format(va)}</td>
                <td className="py-1.5 text-right font-mono tabular-nums">{vb === null || vb === undefined ? '—' : m.format(vb)}</td>
                <td className={`py-1.5 text-right font-mono tabular-nums ${delta ? (better ? 'text-ok' : 'text-block') : 'text-ink-3'}`}>
                  {delta === null ? '—' : `${delta > 0 ? '+' : delta < 0 ? '−' : ''}${m.format(Math.abs(delta))}`}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>

      <p className="mt-8 text-sm text-ink-3">{t('eval.unchanged', { count: data.unchanged })}</p>
      <div className="mt-3 grid gap-8 lg:grid-cols-2">
        <CaseList title={t('eval.improved', { count: data.improved.length })} entries={data.improved} tone="text-ok" />
        <CaseList title={t('eval.regressed', { count: data.regressed.length })} entries={data.regressed} tone="text-block" />
      </div>
    </section>
  )
}
