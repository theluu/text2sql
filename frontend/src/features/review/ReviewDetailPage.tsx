import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from '@tanstack/react-router'
import { ArrowLeft, Play } from 'lucide-react'
import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { DataTable } from '@/features/ask/DataTable'
import { PipelineStrip } from '@/features/ask/PipelineStrip'
import { ApiError } from '@/lib/api'
import { formatNumber, formatPercent } from '@/lib/format'
import { type DryRunResult, reviewApi, useReviewDetail } from './api'
import { ReasonChip } from './ReviewQueuePage'

const SqlDiffEditor = lazy(() => import('./SqlDiffEditor'))

function errorText(t: (k: string, o?: Record<string, unknown>) => string, error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'already_resolved' || error.code === 'claimed_by_other') return t(`review.errors.${error.code}`)
    if (error.code === 'dry_run_failed' || error.status === 422) return t('review.errors.dry_run_failed', { message: error.message })
  }
  return t('review.errors.generic')
}

export function ReviewDetailPage() {
  const { t } = useTranslation()
  const { itemId } = useParams({ from: '/_app/review/$itemId' })
  const client = useQueryClient()
  const { data, isLoading, isError, refetch } = useReviewDetail(itemId)
  const [sql, setSql] = useState('')
  const [note, setNote] = useState('')
  const [golden, setGolden] = useState(false)
  const [dry, setDry] = useState<DryRunResult | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'block'; text: string } | null>(null)
  const noteRef = useRef<HTMLTextAreaElement>(null)
  const claimed = useRef(false)

  const original = data?.original_sql ?? ''
  const open = data ? ['open', 'claimed'].includes(data.status) : false

  useEffect(() => {
    if (data) setSql(data.final_sql ?? data.original_sql ?? '')
  }, [data])

  useEffect(() => {
    if (data?.status === 'open' && !claimed.current) {
      claimed.current = true
      void reviewApi.claim(itemId).catch(() => undefined)
    }
  }, [data?.status, itemId])

  const dryRun = useMutation({
    mutationFn: () => reviewApi.dryRun(itemId, sql),
    onSuccess: (result) => setDry(result),
  })

  const resolve = useMutation({
    mutationFn: async (action: 'approve' | 'edit' | 'reject' | 'return') => {
      if ((action === 'reject' || action === 'return') && !note.trim()) {
        noteRef.current?.focus()
        throw new Error('note')
      }
      if (action === 'approve') return reviewApi.approve(itemId, { note: note || undefined, add_to_golden: golden })
      if (action === 'edit') return reviewApi.edit(itemId, { sql, note: note || undefined, add_to_golden: golden })
      if (action === 'reject') return reviewApi.reject(itemId, note)
      return reviewApi.returnToAsker(itemId, note)
    },
    onSuccess: (result) => {
      setMessage({ tone: 'ok', text: t('review.resolved', { status: t(`review.statuses.${result.status}`) }) })
      void client.invalidateQueries({ queryKey: ['review'] })
    },
    onError: (error) =>
      setMessage({ tone: 'block', text: error instanceof Error && error.message === 'note' ? t('review.noteRequired') : errorText(t, error) }),
  })

  const act = useCallback(
    (action: 'approve' | 'edit' | 'reject' | 'return') => {
      setMessage(null)
      resolve.mutate(action)
    },
    [resolve],
  )

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      if (!open || resolve.isPending || event.metaKey || event.ctrlKey || event.altKey) return
      if (target?.closest('input, textarea, select, [contenteditable="true"], .monaco-editor')) return
      const key = event.key.toLowerCase()
      if (key === 'a') act('approve')
      else if (key === 'e') act('edit')
      else if (key === 'r') act('reject')
      else return
      event.preventDefault()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [act, open, resolve.isPending])

  if (isError)
    return (
      <div className="p-8 text-sm">
        <p className="text-block">{t('review.errors.load')}</p>
        <button type="button" onClick={() => void refetch()} className="mt-2 text-accent hover:underline">{t('common.retry')}</button>
      </div>
    )
  if (isLoading || !data) return <div className="p-8"><div className="h-6 w-1/3 animate-pulse rounded bg-surface-2" /></div>

  const run = data.run
  const edited = sql.trim() !== original.trim()
  const button = 'rounded-[4px] px-3 py-1.5 text-sm font-medium disabled:opacity-40'

  return (
    <section className="grid h-[calc(100vh-3.5rem)] min-w-0 grid-rows-[auto_1fr]">
      <header className="flex items-center gap-4 border-b border-rule px-6 py-3">
        <Link to="/review" className="flex items-center gap-1 text-sm text-ink-2 hover:text-ink">
          <ArrowLeft size={14} /> {t('review.back')}
        </Link>
        <h1 className="min-w-0 flex-1 truncate font-display text-lg font-semibold">{run.question}</h1>
        <span className="hidden shrink-0 text-xs text-ink-3 xl:inline">{t('review.shortcuts')}</span>
      </header>
      <div className="grid min-h-0 grid-cols-1 lg:grid-cols-[minmax(360px,5fr)_7fr]">
        <aside aria-label={t('review.context')} className="min-h-0 min-w-0 space-y-5 overflow-y-auto border-r border-rule p-6">
          <div>
            <p className="text-xs text-ink-3">{t('review.askedBy', { name: data.asker.name, role: t(`auth.roles.${data.asker.role}`) })}</p>
            <p className="mt-1 text-[15px] font-medium">{run.question}</p>
            {run.rewritten_question && <p className="text-xs text-ink-3">{t('ask.rewritten', { question: run.rewritten_question })}</p>}
            <div className="mt-2 flex flex-wrap gap-1">{data.reasons.map((r) => <ReasonChip key={r} code={r} />)}</div>
          </div>
          <PipelineStrip trace={run.trace} />
          <dl className="grid grid-cols-3 gap-3 text-xs">
            <div><dt className="text-ink-3">{t('ask.badges.confidence', { value: '' })}</dt><dd className="font-mono text-sm">{formatPercent(run.confidence)}</dd></div>
            <div><dt className="text-ink-3">Provider</dt><dd className="font-mono text-sm">{run.provider ?? '—'}</dd></div>
            <div><dt className="text-ink-3">Judge</dt><dd className="font-mono text-sm">{run.judge ? `${run.judge.verdict} ${run.judge.score.toFixed(2)}` : '—'}</dd></div>
          </dl>
          {run.judge && run.judge.issues.length > 0 && (
            <div>
              <h2 className="text-xs font-medium text-ink-2">{t('review.judgeIssues')}</h2>
              <ul className="mt-1 space-y-1 text-sm">{run.judge.issues.map((i) => <li key={i}>– {i}</li>)}</ul>
            </div>
          )}
          {run.explanation && <p className="text-sm text-ink-2">{run.explanation}</p>}
          {run.result && (
            <div>
              <h2 className="mb-1.5 text-xs font-medium text-ink-2">{t('review.originalPreview')}</h2>
              <DataTable result={run.result} />
            </div>
          )}
        </aside>

        <div className="grid min-h-0 min-w-0 grid-rows-[auto_minmax(220px,1fr)_auto] overflow-hidden">
          <div className="flex items-center justify-between border-b border-rule px-4 py-2">
            <h2 className="text-xs font-medium text-ink-2">{t('review.editor')}</h2>
            <button type="button" onClick={() => dryRun.mutate()} disabled={!sql.trim() || dryRun.isPending} title={t('review.dryRunHint')} className="flex items-center gap-1.5 rounded-[4px] border border-rule px-2.5 py-1 text-xs hover:border-accent hover:text-accent disabled:opacity-40">
              <Play size={12} /> {t('review.dryRun')}
            </button>
          </div>
          <div className="min-h-0">
            <Suspense fallback={<pre className="h-full overflow-auto p-4 font-mono text-xs">{sql}</pre>}>
              <SqlDiffEditor original={original} value={sql} onChange={setSql} readOnly={!open} />
            </Suspense>
          </div>
          <div className="max-h-[45vh] space-y-3 overflow-y-auto border-t border-rule p-4">
            {dry && (
              <div role="status" className={`rounded-[4px] border px-3 py-2 text-sm ${dry.ok ? 'border-ok/40' : 'border-block/40 bg-block/5'}`}>
                {dry.ok ? (
                  <p className="text-ok">
                    {t('review.dryRunOk', { count: dry.result?.row_count ?? 0 })}
                    {dry.cost !== null && <span className="font-mono text-ink-3"> · cost {formatNumber(dry.cost, 0)}</span>}
                    {dry.pii_columns.length > 0 && <span className="text-warn"> · PII {dry.pii_columns.join(', ')}</span>}
                  </p>
                ) : (
                  <p className="text-block">{dry.code}: {dry.message}</p>
                )}
                {dry.ok && dry.result && dry.result.row_count > 0 && <div className="mt-2"><DataTable result={dry.result} /></div>}
              </div>
            )}
            {open ? (
              <>
                <label className="block text-xs font-medium text-ink-2">
                  {t('review.note')}
                  <textarea ref={noteRef} value={note} onChange={(e) => setNote(e.target.value)} rows={2} placeholder={t('review.notePlaceholder')} className="mt-1 w-full rounded-[4px] border border-rule bg-surface px-2 py-1.5 text-sm font-normal text-ink focus:border-accent focus:outline-none" />
                </label>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <label className="flex items-center gap-2 text-sm text-ink-2">
                    <input type="checkbox" checked={golden} onChange={(e) => setGolden(e.target.checked)} className="accent-[var(--accent)]" />
                    {t('review.golden')}
                  </label>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => act('return')} disabled={resolve.isPending} className={`${button} border border-rule text-ink-2 hover:text-ink`}>{t('review.return')}</button>
                    <button type="button" onClick={() => act('reject')} disabled={resolve.isPending} className={`${button} border border-block/50 text-block hover:bg-block/10`}>{t('review.reject')}</button>
                    <button type="button" onClick={() => act('edit')} disabled={resolve.isPending || !edited} className={`${button} border border-accent text-accent hover:bg-accent/10`}>{t('review.edit')}</button>
                    <button type="button" onClick={() => act('approve')} disabled={resolve.isPending || edited} className={`${button} bg-accent text-accent-ink`}>{t('review.approve')}</button>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-sm text-ink-2">
                {t('review.resolved', { status: t(`review.statuses.${data.status}`) })}
                {data.note && <span className="block text-ink-3">{data.note}</span>}
              </p>
            )}
            {message && <p role="alert" className={`text-sm ${message.tone === 'ok' ? 'text-ok' : 'text-block'}`}>{message.text}</p>}
          </div>
        </div>
      </div>
    </section>
  )
}
