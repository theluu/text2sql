import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { TFunction } from 'i18next'
import { Link, useNavigate } from '@tanstack/react-router'
import { Play } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatMs, formatUsd, relativeTime } from '@/lib/format'
import { evalKeys, type EvalRun, startRun, useEvalModes, useEvalRuns } from './api'
import { pct } from './Kpi'

export function modeLabel(t: TFunction, mode: string): string {
  return mode.startsWith('provider=') ? mode.replace('provider=', '') : t(`eval.modes.${mode}`, mode)
}

function Progress({ run }: { run: EvalRun }) {
  const { t } = useTranslation()
  if (run.status !== 'running' && run.status !== 'queued') {
    const tone = run.status === 'done' ? 'text-ok' : 'text-block'
    return <span className={`text-xs font-medium ${tone}`}>{t(`eval.status.${run.status}`)}</span>
  }
  const ratio = run.total ? (run.done ?? 0) / run.total : 0
  return (
    <span className="flex items-center gap-2" aria-label={t('eval.progress', { done: run.done ?? 0, total: run.total })}>
      <span className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
        <span className="block h-full bg-accent transition-[width]" style={{ width: `${ratio * 100}%` }} />
      </span>
      <span className="font-mono text-[11px] text-ink-3">{run.done ?? 0}/{run.total}</span>
    </span>
  )
}

export function EvalPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const client = useQueryClient()
  const runs = useEvalRuns()
  const modes = useEvalModes()
  const [suite, setSuite] = useState('smoke')
  const [mode, setMode] = useState('chain')
  const [selected, setSelected] = useState<string[]>([])
  const start = useMutation({
    mutationFn: () => startRun(suite, mode),
    onSuccess: () => void client.invalidateQueries({ queryKey: evalKeys.runs }),
  })
  const select = 'rounded-[4px] border border-rule bg-surface px-2 py-1.5 text-sm'

  const toggle = (id: string) =>
    setSelected((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id].slice(-2)))

  return (
    <section className="px-8 py-8">
      <h1 className="font-display text-3xl font-semibold tracking-tight">{t('eval.title')}</h1>
      <p className="mt-1 max-w-3xl text-sm text-ink-2">{t('eval.subtitle')}</p>

      <form
        className="mt-6 flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault()
          start.mutate()
        }}
      >
        <label className="text-xs text-ink-2">
          {t('eval.suite')}
          <select value={suite} onChange={(e) => setSuite(e.target.value)} className={`mt-1 block ${select}`}>
            {(modes.data?.suites ?? ['smoke', 'full']).map((s) => (
              <option key={s} value={s}>{t(`eval.suites.${s}`, s)}</option>
            ))}
          </select>
        </label>
        <label className="text-xs text-ink-2">
          {t('eval.mode')}
          <select value={mode} onChange={(e) => setMode(e.target.value)} className={`mt-1 block ${select}`}>
            {(modes.data?.modes ?? ['chain', 'rule_based']).map((m) => (
              <option key={m} value={m}>{modeLabel(t, m)}</option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={start.isPending} className="flex items-center gap-1.5 rounded-[4px] bg-accent px-3 py-2 text-sm font-medium text-accent-ink disabled:opacity-50">
          <Play size={14} aria-hidden /> {start.isPending ? t('eval.starting') : t('eval.run')}
        </button>
        <button
          type="button"
          disabled={selected.length !== 2}
          title={t('eval.compareHint')}
          onClick={() => void navigate({ to: '/eval/compare', search: { a: selected[0], b: selected[1] } })}
          className="ml-auto rounded-[4px] border border-rule px-3 py-2 text-sm text-ink-2 hover:text-ink disabled:opacity-40"
        >
          {t('eval.compare')}
        </button>
      </form>

      <h2 className="mt-8 text-sm font-medium text-ink-2">{t('eval.runs')}</h2>
      <div className="mt-2 overflow-x-auto rounded-[6px] border border-rule bg-surface">
        <table className="w-full text-sm">
          <thead className="border-b border-rule bg-surface-2 text-left text-xs text-ink-2">
            <tr>
              <th className="w-8 px-3 py-2" aria-label={t('eval.compare')} />
              {(['started', 'suite', 'mode', 'status', 'ex', 'behavior', 'guardrail', 'p95', 'cost', 'commit'] as const).map((c) => (
                <th key={c} scope="col" className={`px-3 py-2 font-medium ${['ex', 'behavior', 'guardrail', 'p95', 'cost'].includes(c) ? 'text-right' : ''}`}>
                  {t(`eval.columns.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.data?.length === 0 && (
              <tr><td colSpan={11} className="px-3 py-10 text-center text-ink-3">{t('eval.noRuns')}</td></tr>
            )}
            {runs.data?.map((run) => {
              const s = run.summary
              return (
                <tr key={run.id} className="border-b border-rule/70 last:border-0 hover:bg-surface-2/50">
                  <td className="px-3 py-2.5">
                    <input type="checkbox" checked={selected.includes(run.id)} onChange={() => toggle(run.id)} aria-label={`${t('eval.compare')} ${run.id.slice(0, 8)}`} className="accent-[var(--accent)]" />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2.5">
                    <Link to="/eval/$runId" params={{ runId: run.id }} className="font-medium hover:text-accent">
                      {relativeTime(run.started_at)}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5">{t(`eval.suites.${run.suite}`, run.suite)}</td>
                  <td className="px-3 py-2.5 text-ink-2">{modeLabel(t, run.mode)}</td>
                  <td className="px-3 py-2.5"><Progress run={run} /></td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{pct(s?.ex)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums">{pct(s?.behavior_accuracy)}</td>
                  <td className={`px-3 py-2.5 text-right font-mono tabular-nums ${s && s.adversarial_leaks.length ? 'text-block' : ''}`}>{pct(s?.guardrail_recall, 0)}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums text-ink-2">{s ? formatMs(s.latency_p95_ms) : '—'}</td>
                  <td className="px-3 py-2.5 text-right font-mono tabular-nums text-ink-2">{s ? formatUsd(s.cost_per_query_usd) : '—'}</td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-ink-3">{run.git_sha?.slice(0, 7) ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
