import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, ShieldAlert, ThumbsDown, ThumbsUp } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { downloadText, formatPercent, toCsv } from '@/lib/format'
import { conversationKeys, sendFeedback } from './api'
import { DataTable } from './DataTable'
import { PipelineStrip } from './PipelineStrip'
import { ResultChart } from './ResultChart'
import { SqlBlock } from './SqlBlock'
import type { RunView, TraceStep } from './types'

const STATUS_TONE: Record<string, string> = {
  answered: 'text-ok',
  pending_review: 'text-warn',
  rejected: 'text-block',
  failed: 'text-ink-2',
  running: 'text-accent',
}

function Badge({ children, tone = 'border-rule text-ink-2' }: { children: React.ReactNode; tone?: string }) {
  return <span className={`rounded-[3px] border px-1.5 py-0.5 text-[11px] ${tone}`}>{children}</span>
}

function Feedback({ run }: { run: RunView }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [rating, setRating] = useState(run.feedback)
  const mutation = useMutation({
    mutationFn: (value: 'up' | 'down') => sendFeedback(run.id, value),
    onSuccess: (_, value) => {
      setRating(value)
      if (run.conversation_id) void client.invalidateQueries({ queryKey: conversationKeys.detail(run.conversation_id) })
    },
  })
  return (
    <div className="flex items-center gap-1">
      {(['up', 'down'] as const).map((value) => {
        const Icon = value === 'up' ? ThumbsUp : ThumbsDown
        const active = rating === value
        return (
          <button
            key={value}
            type="button"
            aria-pressed={active}
            aria-label={t(`ask.feedback.${value}`)}
            title={t(`ask.feedback.${value}`)}
            disabled={mutation.isPending || rating !== null}
            onClick={() => mutation.mutate(value)}
            className={`grid h-7 w-7 place-items-center rounded-[4px] border ${
              active ? (value === 'up' ? 'border-ok text-ok' : 'border-block text-block') : 'border-transparent text-ink-3 hover:text-ink'
            } disabled:cursor-default`}
          >
            <Icon size={14} />
          </button>
        )
      })}
      {rating && (
        <span className="text-xs text-ink-3" role="status">
          {rating === 'down' ? t('ask.feedback.downSent') : t('ask.feedback.thanks')}
        </span>
      )}
    </div>
  )
}

export function RunCard({
  run,
  question,
  liveSteps,
  onOpenTrace,
  onAsk,
}: {
  run: RunView | null
  question: string
  liveSteps?: TraceStep[]
  onOpenTrace: () => void
  onAsk: (question: string) => void
}) {
  const { t } = useTranslation()
  const live = run === null
  const trace = live ? liveSteps ?? [] : run.trace
  const status = run?.status ?? 'running'
  const result = run?.result ?? null

  return (
    <article className="border-b border-rule py-6 first:pt-2" aria-busy={live}>
      <header className="flex items-start justify-between gap-4">
        <h3 className="font-display text-xl font-semibold leading-snug tracking-tight">{question}</h3>
        <span className={`shrink-0 pt-1 text-xs font-medium ${STATUS_TONE[status]}`}>{t(`ask.status.${status}`)}</span>
      </header>
      {run?.rewritten_question && <p className="mt-1 text-xs text-ink-3">{t('ask.rewritten', { question: run.rewritten_question })}</p>}
      <div className="mt-3">
        <PipelineStrip trace={trace} live={live} onOpen={onOpenTrace} />
      </div>

      {run && (
        <div className="mt-4 space-y-4">
          {run.message && (
            <div
              role={status === 'rejected' ? 'alert' : 'status'}
              className={`flex gap-2 rounded-[4px] border px-3 py-2 text-sm ${
                status === 'pending_review'
                  ? 'border-warn/40 bg-warn/10 text-ink'
                  : status === 'rejected'
                    ? 'border-block/40 bg-block/10 text-ink'
                    : 'border-rule bg-surface-2 text-ink'
              }`}
            >
              {status === 'rejected' && <ShieldAlert size={16} className="mt-0.5 shrink-0 text-block" aria-hidden />}
              <div>
                <p>{run.message}</p>
                {run.reasons.length > 0 && (
                  <ul className="mt-1 list-inside list-disc text-xs text-ink-2">
                    {run.reasons.map((r) => (
                      <li key={r.code}>{r.label}</li>
                    ))}
                  </ul>
                )}
                {run.review?.note && <p className="mt-1 text-xs text-ink-2">{t('ask.reviewNote', { note: run.review.note })}</p>}
              </div>
            </div>
          )}

          {run.summary && <p className="text-[15px] leading-relaxed text-ink">{run.summary}</p>}

          {result && result.row_count === 0 && <p className="text-sm text-ink-3">{t('ask.noData')}</p>}
          {result && result.row_count > 0 && (
            <>
              {result.draft && <p className="text-xs font-medium text-warn">{t('ask.draft')}</p>}
              {run.chart && <ResultChart spec={run.chart} result={result} />}
              {!(run.chart?.type === 'kpi') && <DataTable result={result} />}
              {result.truncated && <p className="text-xs text-ink-3">{t('ask.truncated', { count: result.row_count })}</p>}
            </>
          )}

          {run.sql && <SqlBlock sql={run.sql} explanation={run.explanation} open={status === 'pending_review'} />}

          {run.suggestions && run.suggestions.length > 0 && (
            <div>
              <p className="text-xs text-ink-3">{t('ask.suggestionsTitle')}</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {run.suggestions.map((s) => (
                  <button key={s} type="button" onClick={() => onAsk(s)} className="rounded-[4px] border border-rule bg-surface px-2 py-1 text-xs hover:border-accent hover:text-accent">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {(status === 'answered' || status === 'pending_review') && (
            <footer className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-1.5">
                {run.confidence !== null && <Badge>{t('ask.badges.confidence', { value: formatPercent(run.confidence) })}</Badge>}
                {run.used_fallback && <Badge tone="border-fallback/50 text-fallback">{t('ask.badges.fallback')}</Badge>}
                {run.provider === 'verified_example' && <Badge tone="border-ok/50 text-ok">{t('ask.badges.verified')}</Badge>}
                {run.provider && !run.used_fallback && run.provider !== 'verified_example' && (
                  <Badge>{t('ask.badges.provider', { value: run.provider })}</Badge>
                )}
                {run.cache_hit && <Badge>{t('ask.badges.cache')}</Badge>}
                {run.review?.edited && <Badge tone="border-ok/50 text-ok">{t('ask.editedByReviewer')}</Badge>}
              </div>
              <div className="flex items-center gap-2">
                {result && result.row_count > 0 && !result.draft && (
                  <button
                    type="button"
                    onClick={() => downloadText(`datum-${run.id.slice(0, 8)}.csv`, toCsv(result.columns, result.rows))}
                    className="flex items-center gap-1.5 rounded-[4px] border border-rule px-2 py-1 text-xs text-ink-2 hover:text-ink"
                  >
                    <Download size={13} aria-hidden />
                    {t('ask.exportCsv')}
                  </button>
                )}
                {status === 'answered' && <Feedback run={run} />}
              </div>
            </footer>
          )}
        </div>
      )}
    </article>
  )
}
