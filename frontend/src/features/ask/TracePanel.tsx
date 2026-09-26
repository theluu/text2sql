import { X } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { formatMs, formatNumber, formatPercent, formatUsd } from '@/lib/format'
import { orderedSteps } from './PipelineStrip'
import type { RunView, TraceStep } from './types'

type Detail = Record<string, unknown>

const DOT: Record<string, string> = { ok: 'bg-ok', error: 'bg-block', skip: 'bg-rule', start: 'bg-accent animate-pulse' }

function Chip({ children, tone = 'text-ink-2' }: { children: ReactNode; tone?: string }) {
  return <span className={`rounded-[3px] border border-rule px-1.5 py-px font-mono text-[11px] ${tone}`}>{children}</span>
}

function asArray(value: unknown): Detail[] {
  return Array.isArray(value) ? (value as Detail[]) : []
}

function StepDetail({ step }: { step: TraceStep }) {
  const { t } = useTranslation()
  const d: Detail = step.detail ?? {}
  if (d.error && step.status === 'error' && step.step !== 'repair') {
    return <p className="text-block">{String(d.message ?? d.error)}</p>
  }
  switch (step.step) {
    case 'input_guard':
      return (
        <p className="text-ink-3">
          {d.code ? <span className="text-block">{String(d.code)}</span> : `lang=${String(d.lang ?? '')}`}
          {d.classifier ? ` · classifier=${String(d.classifier)}` : ''}
        </p>
      )
    case 'rewrite':
      return <p className="text-ink-2">{String(d.question ?? '')}</p>
    case 'cache':
      return <p className="text-ink-3">{d.hit ? 'hit' : 'miss'}</p>
    case 'link':
      return (
        <div className="flex flex-wrap gap-1">
          {(d.tables as string[] | undefined)?.map((table) => <Chip key={table}>{table}</Chip>)}
          {(d.metrics as string[] | undefined)?.map((m) => (
            <Chip key={m} tone="text-accent">
              {m}
            </Chip>
          ))}
        </div>
      )
    case 'fewshot':
      return (
        <ul className="space-y-0.5 text-ink-2">
          {asArray(d.examples).map((e) => (
            <li key={String(e.id)} className="truncate">
              {String(e.question)}{' '}
              <span className="text-ink-3">({t('trace.similarity', { value: formatPercent(Number(e.similarity)) })})</span>
            </li>
          ))}
          {asArray(d.examples).length === 0 && <li className="text-ink-3">—</li>}
        </ul>
      )
    case 'generate': {
      const attempts = asArray(d.attempts)
      return (
        <div className="space-y-1">
          <p className="text-ink-2">
            {String(d.source)} {d.provider ? `· ${String(d.provider)}` : ''} {d.model ? `· ${String(d.model)}` : ''}
            {d.intent ? `· ${String(d.intent)}` : ''}
          </p>
          {attempts.length > 1 && (
            <div className="flex flex-wrap gap-1">
              {attempts.map((a, i) => (
                <Chip key={i} tone={a.outcome === 'ok' ? 'text-ok' : 'text-block'}>
                  {String(a.provider)}#{String(a.attempt)} {String(a.outcome)}
                </Chip>
              ))}
            </div>
          )}
          {d.failover === true && <p className="text-fallback">{t('trace.failover')}</p>}
          {typeof d.llm_error === 'string' && <p className="text-fallback">{d.llm_error}</p>}
        </div>
      )
    }
    case 'validate':
      return (
        <div className="flex flex-wrap gap-1">
          {(d.tables as string[] | undefined)?.map((table) => <Chip key={table}>{table}</Chip>)}
          {(d.pii_columns as string[] | undefined)?.map((c) => (
            <Chip key={c} tone="text-warn">
              PII {c}
            </Chip>
          ))}
        </div>
      )
    case 'cost':
      return (
        <p className="font-mono text-ink-2">
          {formatNumber(Number(d.cost ?? 0), 0)}
          <span className="text-ink-3"> / {formatNumber(Number(d.gray ?? 0), 0)}</span>
        </p>
      )
    case 'execute':
      return <p className="font-mono text-ink-2">{t('ask.rowsCount', { count: Number(d.rows ?? 0) })}</p>
    case 'repair':
      return (
        <p className={d.fixed ? 'text-ink-2' : 'text-block'}>
          #{String(d.attempt)} {String(d.error ?? '')}
        </p>
      )
    case 'judge': {
      const rubric = (d.rubric ?? {}) as Record<string, { score: number; reason: string }>
      const verdict = String(d.verdict ?? 'uncertain')
      const tone = verdict === 'pass' ? 'text-ok' : verdict === 'fail' ? 'text-block' : 'text-warn'
      return (
        <div className="space-y-2">
          <p>
            <span className={`font-medium ${tone}`}>{t(`trace.verdict.${verdict}`)}</span>
            <span className="font-mono text-ink-3"> {Number(d.score ?? 0).toFixed(2)} · {String(d.model ?? '')}</span>
          </p>
          {d.same_vendor === true && <p className="text-warn">{t('trace.sameVendor')}</p>}
          <dl className="space-y-1">
            {Object.entries(rubric).map(([name, item]) => (
              <div key={name} className="grid grid-cols-[96px_1fr_16px] items-center gap-2" title={item.reason}>
                <dt className="truncate text-ink-3">{t(`trace.rubric.${name}`)}</dt>
                <dd className="flex gap-[2px]" aria-label={`${item.score}/5`}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <span key={n} className={`h-1.5 flex-1 ${n <= item.score ? (item.score >= 4 ? 'bg-ok' : item.score >= 3 ? 'bg-warn' : 'bg-block') : 'bg-surface-2'}`} />
                  ))}
                </dd>
                <span className="font-mono text-ink-3">{item.score}</span>
              </div>
            ))}
          </dl>
          {(d.issues as string[] | undefined)?.map((issue) => (
            <p key={issue} className="text-ink-2">
              – {issue}
            </p>
          ))}
        </div>
      )
    }
    case 'consistency':
      return <p className="text-ink-2">{t('trace.agreement', { value: formatPercent(Number(d.agreement)) })}</p>
    case 'risk': {
      const decision = String(d.decision ?? '')
      const tone = decision === 'AUTO_EXECUTE' ? 'text-ok' : decision === 'REJECT' ? 'text-block' : 'text-warn'
      return (
        <div className="space-y-1">
          <p>
            <span className={`font-medium ${tone}`}>{t(`trace.decision.${decision}`, decision)}</span>
            <span className="font-mono text-ink-3"> · {formatPercent(Number(d.confidence))}</span>
          </p>
          <div className="flex flex-wrap gap-1">
            {(d.reasons as string[] | undefined)?.map((r) => (
              <Chip key={r} tone="text-warn">
                {r}
              </Chip>
            ))}
          </div>
        </div>
      )
    }
    case 'output':
      return (
        <p className="text-ink-3">
          {String(d.chart ?? '')}
          {(d.masked as string[] | undefined)?.length ? ` · masked ${(d.masked as string[]).join(', ')}` : ''}
        </p>
      )
    default:
      return null
  }
}

export function TracePanel({ run, trace, onClose }: { run: RunView | null; trace: TraceStep[]; onClose: () => void }) {
  const { t } = useTranslation()
  const steps = orderedSteps(trace).filter((s) => s.detail?.pending !== true || trace.length === 0)
  return (
    <aside aria-label={t('trace.title')} className="flex h-full flex-col border-l border-rule bg-surface">
      <header className="flex h-12 items-center justify-between border-b border-rule px-4">
        <h2 className="font-display text-base font-semibold">{t('trace.title')}</h2>
        <button type="button" onClick={onClose} aria-label={t('trace.close')} className="text-ink-3 hover:text-ink">
          <X size={16} />
        </button>
      </header>
      {trace.length === 0 ? (
        <p className="p-4 text-sm text-ink-3">{t('trace.empty')}</p>
      ) : (
        <ol className="flex-1 overflow-y-auto px-4 py-3">
          {steps.map((step, i) => (
            <li key={`${step.step}-${i}`} className="relative border-l border-rule pb-4 pl-4 last:pb-1">
              <span
                aria-hidden
                className={`absolute -left-[4.5px] top-1.5 h-2 w-2 rounded-full ${DOT[step.status] ?? 'bg-rule'}`}
              />
              <div className="flex items-baseline justify-between gap-2 text-[13px]">
                <span className={step.status === 'skip' ? 'text-ink-3' : 'font-medium text-ink'}>
                  {t(`trace.steps.${step.step}`)}
                </span>
                <span className="font-mono text-[11px] text-ink-3">
                  {step.status === 'skip' ? t('trace.skipped') : formatMs(step.duration_ms)}
                </span>
              </div>
              {step.status !== 'skip' && (
                <div className="mt-1 text-xs leading-relaxed">
                  <StepDetail step={step} />
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      {run && (
        <footer className="grid grid-cols-2 gap-2 border-t border-rule px-4 py-3 text-xs">
          <div>
            <p className="text-ink-3">{t('trace.total')}</p>
            <p className="font-mono text-ink">{formatMs(run.latency_ms)}</p>
          </div>
          <div>
            <p className="text-ink-3">{t('trace.cost')}</p>
            <p className="font-mono text-ink">{formatUsd(run.cost_usd)}</p>
          </div>
        </footer>
      )}
    </aside>
  )
}
