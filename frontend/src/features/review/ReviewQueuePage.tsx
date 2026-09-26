import { Link } from '@tanstack/react-router'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatPercent, relativeTime } from '@/lib/format'
import { useReviewQueue } from './api'

const STATUSES = ['pending', 'approved', 'edited', 'rejected', 'returned', 'all']
const REASONS = ['PII_ACCESS', 'JUDGE_FAIL', 'JUDGE_UNCERTAIN', 'LOW_CONFIDENCE', 'FALLBACK_LOW_CONFIDENCE', 'COST_GRAY', 'USER_DOWNVOTE']
const STATUS_TONE: Record<string, string> = {
  open: 'text-warn', claimed: 'text-accent', approved: 'text-ok', edited: 'text-ok', rejected: 'text-block', returned: 'text-ink-2',
}

export function ReasonChip({ code }: { code: string }) {
  const { t } = useTranslation()
  const tone = code === 'PII_ACCESS' || code === 'JUDGE_FAIL' ? 'border-block/40 text-block' : 'border-warn/40 text-warn'
  return (
    <span title={code} className={`whitespace-nowrap rounded-[3px] border px-1.5 py-px text-[11px] ${tone}`}>
      {t(`reasons.${code}`, code)}
    </span>
  )
}

export function ReviewQueuePage() {
  const { t } = useTranslation()
  const [status, setStatus] = useState('pending')
  const [reason, setReason] = useState('')
  const { data, isLoading } = useReviewQueue(status, reason)
  const select = 'rounded-[4px] border border-rule bg-surface px-2 py-1 text-sm'

  return (
    <section className="px-8 py-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">{t('review.title')}</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-2">{t('review.subtitle')}</p>
        </div>
        <div className="flex gap-3 text-sm">
          <label className="flex items-center gap-2 text-ink-2">
            {t('review.filters.status')}
            <select value={status} onChange={(e) => setStatus(e.target.value)} className={select}>
              {STATUSES.map((s) => (
                <option key={s} value={s}>{t(`review.statuses.${s}`)}</option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 text-ink-2">
            {t('review.filters.reason')}
            <select value={reason} onChange={(e) => setReason(e.target.value)} className={select}>
              <option value="">{t('review.filters.all')}</option>
              {REASONS.map((r) => (
                <option key={r} value={r}>{t(`reasons.${r}`, r)}</option>
              ))}
            </select>
          </label>
        </div>
      </header>

      <div className="mt-6 overflow-x-auto rounded-[6px] border border-rule bg-surface">
        <table className="w-full text-sm">
          <thead className="border-b border-rule bg-surface-2 text-left text-xs text-ink-2">
            <tr>
              {(['priority', 'question', 'asker', 'reasons', 'status', 'age', 'assignee'] as const).map((c) => (
                <th key={c} scope="col" className={`px-3 py-2 font-medium ${c === 'priority' ? 'w-20 text-right' : ''}`}>
                  {t(`review.columns.${c}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={7} className="px-3 py-6"><div className="h-4 w-1/2 animate-pulse rounded bg-surface-2" /></td></tr>
            )}
            {data?.items.length === 0 && (
              <tr><td colSpan={7} className="px-3 py-10 text-center text-ink-3">{t('review.empty')}</td></tr>
            )}
            {data?.items.map((item) => (
              <tr key={item.id} className="border-b border-rule/70 last:border-0 hover:bg-surface-2/50">
                <td className="px-3 py-2.5 text-right font-mono tabular-nums">{item.priority.toFixed(1)}</td>
                <td className="max-w-[420px] px-3 py-2.5">
                  <Link to="/review/$itemId" params={{ itemId: item.id }} className="line-clamp-2 font-medium text-ink hover:text-accent">
                    {item.question}
                  </Link>
                  {item.confidence !== null && <span className="font-mono text-[11px] text-ink-3">{formatPercent(item.confidence)} · {item.provider}</span>}
                </td>
                <td className="px-3 py-2.5 text-ink-2">
                  {item.asker.name}
                  <span className="block text-[11px] text-ink-3">{t(`auth.roles.${item.asker.role}`)}</span>
                </td>
                <td className="px-3 py-2.5"><div className="flex flex-wrap gap-1">{item.reasons.map((r) => <ReasonChip key={r} code={r} />)}</div></td>
                <td className={`px-3 py-2.5 text-xs font-medium ${STATUS_TONE[item.status] ?? ''}`}>{t(`review.statuses.${item.status}`)}</td>
                <td className="whitespace-nowrap px-3 py-2.5 font-mono text-[11px] text-ink-3">{relativeTime(item.created_at)}</td>
                <td className="px-3 py-2.5 text-xs text-ink-2">{item.assignee ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
