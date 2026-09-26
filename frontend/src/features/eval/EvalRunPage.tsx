import { Link, useParams } from '@tanstack/react-router'
import { ArrowLeft } from 'lucide-react'
import { Fragment, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatMs, formatUsd } from '@/lib/format'
import { type Breakdown, useEvalRun } from './api'
import { modeLabel } from './EvalPage'
import { Kpi, MeterCell, pct } from './Kpi'

function BreakdownTable({ title, rows, labelOf }: { title: string; rows: Record<string, Breakdown>; labelOf: (k: string) => string }) {
  const { t } = useTranslation()
  return (
    <div>
      <h2 className="text-sm font-medium text-ink-2">{title}</h2>
      <table className="mt-2 w-full text-sm">
        <thead className="text-left text-xs text-ink-3">
          <tr>
            <th className="py-1 font-medium">{t('eval.group')}</th>
            <th className="py-1 text-right font-medium">{t('eval.cases')}</th>
            <th className="py-1 pl-4 font-medium">EX</th>
            <th className="py-1 font-medium">{t('eval.columns.behavior')}</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(rows)
            .sort(([a], [b]) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99))
            .map(([key, row]) => (
            <tr key={key} className="border-t border-rule/70">
              <td className="py-1.5">{labelOf(key)}</td>
              <td className="py-1.5 text-right font-mono text-xs text-ink-2">{row.n}</td>
              <td className="py-1.5 pl-4"><MeterCell value={row.ex} /></td>
              <td className="py-1.5"><MeterCell value={row.behavior} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const ORDER = ['easy', 'medium', 'hard', 'extra']
const mark = (ok: boolean | null) => (ok === null ? <span className="text-ink-3">—</span> : ok ? <span className="text-ok">✓</span> : <span className="text-block">✗</span>)

export function EvalRunPage() {
  const { t } = useTranslation()
  const { runId } = useParams({ from: '/_app/eval/$runId' })
  const { data } = useEvalRun(runId)
  const [failuresOnly, setFailuresOnly] = useState(false)
  const [open, setOpen] = useState<string | null>(null)
  if (!data) return <div className="p-8"><div className="h-6 w-1/3 animate-pulse rounded bg-surface-2" /></div>

  const s = data.summary
  const running = data.status === 'running' || data.status === 'queued'
  const results = data.results.filter((r) => !failuresOnly || r.behavior !== r.expected || r.ex === false)

  return (
    <section className="px-8 py-8">
      <Link to="/eval" className="flex items-center gap-1 text-sm text-ink-2 hover:text-ink"><ArrowLeft size={14} /> {t('eval.back')}</Link>
      <h1 className="mt-3 font-display text-3xl font-semibold tracking-tight">
        {t(`eval.suites.${data.suite}`, data.suite)} — {modeLabel(t, data.mode)}
      </h1>
      <p className="mt-1 font-mono text-xs text-ink-3">
        {t('eval.meta', { suite: data.suite, mode: data.mode, prompt: data.prompt_version, sha: data.git_sha?.slice(0, 7) ?? '—' })}
      </p>
      {data.model_chain.length > 0 && <p className="font-mono text-xs text-ink-3">{t('eval.chain', { chain: data.model_chain.join(' → ') })}</p>}

      {running && (
        <div className="mt-6" role="status">
          <p className="text-sm text-ink-2">{t('eval.progress', { done: data.results.length, total: data.total })}</p>
          <div className="mt-1 h-1.5 w-full max-w-md overflow-hidden rounded-full bg-surface-2">
            <div className="h-full bg-accent transition-[width]" style={{ width: `${data.total ? (data.results.length / data.total) * 100 : 0}%` }} />
          </div>
        </div>
      )}

      {s && (
        <>
          <div className="mt-8 grid grid-cols-2 gap-y-6 md:grid-cols-4 xl:grid-cols-7">
            <Kpi label={t('eval.kpi.ex')} value={pct(s.ex)} hint={t('eval.kpi.exHint')} />
            <Kpi label={t('eval.kpi.behavior')} value={pct(s.behavior_accuracy)} hint={t('eval.kpi.behaviorHint')} />
            <Kpi label={t('eval.kpi.guardrail')} value={pct(s.guardrail_recall, 0)} tone={s.adversarial_leaks.length ? 'block' : 'ok'} />
            <Kpi label={t('eval.kpi.kappa')} value={s.judge_kappa?.toFixed(2) ?? '—'} hint={t('eval.kpi.kappaHint')} />
            <Kpi label={t('eval.kpi.p95')} value={formatMs(s.latency_p95_ms)} hint={`p50 ${formatMs(s.latency_p50_ms)}`} />
            <Kpi label={t('eval.kpi.cost')} value={formatUsd(s.cost_per_query_usd)} />
            <Kpi label={t('eval.kpi.fallback')} value={pct(s.fallback_rate, 0)} hint={`${t('eval.kpi.linking')} ${pct(s.linking_recall, 0)}`} />
          </div>
          {s.adversarial_leaks.length > 0 && (
            <p role="alert" className="mt-4 rounded-[4px] border border-block/40 bg-block/10 px-3 py-2 text-sm">
              {t('eval.leaks', { keys: s.adversarial_leaks.join(', ') })}
            </p>
          )}
          <div className="mt-10 grid gap-10 lg:grid-cols-2">
            <BreakdownTable title={t('eval.byDifficulty')} rows={s.by_difficulty} labelOf={(k) => t(`eval.difficulty.${k}`, k)} />
            <BreakdownTable title={t('eval.byTag')} rows={s.by_tag} labelOf={(k) => k} />
          </div>
        </>
      )}

      <div className="mt-10 flex items-center justify-between">
        <h2 className="text-sm font-medium text-ink-2">{t('eval.caseTable')}</h2>
        <div role="group" className="flex rounded-[4px] border border-rule p-0.5 text-xs">
          {([false, true] as const).map((value) => (
            <button key={String(value)} type="button" aria-pressed={failuresOnly === value} onClick={() => setFailuresOnly(value)}
              className={`rounded-[3px] px-2 py-0.5 ${failuresOnly === value ? 'bg-ink text-paper' : 'text-ink-2'}`}>
              {t(value ? 'eval.filter.failures' : 'eval.filter.all')}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-2 overflow-x-auto rounded-[6px] border border-rule bg-surface">
        <table className="w-full text-sm">
          <thead className="border-b border-rule bg-surface-2 text-left text-xs text-ink-2">
            <tr>
              {(['key', 'question', 'expected', 'behavior', 'ex', 'judge', 'provider', 'latency'] as const).map((c) => (
                <th key={c} scope="col" className="px-3 py-2 font-medium">{t(`eval.caseColumns.${c}`)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {results.map((r) => {
              const wrong = r.behavior !== r.expected || r.ex === false
              return (
                <Fragment key={r.key}>
                  <tr onClick={() => setOpen(open === r.key ? null : r.key)} className={`cursor-pointer border-b border-rule/70 hover:bg-surface-2/50 ${wrong ? 'bg-block/5' : ''}`}>
                    <td className="px-3 py-2 font-mono text-xs">{r.key}</td>
                    <td className="max-w-[420px] px-3 py-2"><span className="line-clamp-1">{r.question}</span></td>
                    <td className="px-3 py-2 text-xs text-ink-2">{t(`eval.behaviors.${r.expected}`)}</td>
                    <td className={`px-3 py-2 text-xs ${r.behavior === r.expected ? 'text-ink-2' : 'font-medium text-block'}`}>{t(`eval.behaviors.${r.behavior}`)}</td>
                    <td className="px-3 py-2">{mark(r.ex)}</td>
                    <td className="px-3 py-2 text-xs text-ink-2">{r.judge ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-2">{r.provider ?? r.guardrail_code ?? '—'}</td>
                    <td className="px-3 py-2 font-mono text-[11px] text-ink-3">{formatMs(r.latency_ms)}</td>
                  </tr>
                  {open === r.key && (
                    <tr className="border-b border-rule/70 bg-paper/60">
                      <td colSpan={8} className="px-3 py-3">
                        <div className="grid gap-3 md:grid-cols-2">
                          {(['gold', 'predicted'] as const).map((kind) => (
                            <div key={kind}>
                              <p className="text-xs font-medium text-ink-2">{t(`eval.${kind}`)}</p>
                              <pre className="mt-1 whitespace-pre-wrap break-words rounded-[4px] border border-rule bg-surface p-2 font-mono text-[11.5px]">
                                {(kind === 'gold' ? r.gold_sql : r.predicted_sql) ?? t('eval.none')}
                              </pre>
                            </div>
                          ))}
                        </div>
                        {r.error && <p className="mt-2 text-xs text-block">{r.error}</p>}
                      </td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
