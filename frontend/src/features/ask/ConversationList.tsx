import { Link } from '@tanstack/react-router'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { relativeTime } from '@/lib/format'
import { useConversations } from './api'

export function ConversationList({ activeId }: { activeId?: string }) {
  const { t } = useTranslation()
  const { data, isLoading } = useConversations()
  return (
    <nav aria-label={t('ask.history')} className="flex h-full flex-col border-r border-rule">
      <div className="p-3">
        <Link
          to="/"
          className="flex items-center justify-center gap-1.5 rounded-[4px] border border-rule bg-surface px-3 py-2 text-sm font-medium hover:border-accent hover:text-accent"
        >
          <Plus size={14} aria-hidden />
          {t('ask.newChat')}
        </Link>
      </div>
      <h2 className="px-4 pb-1 pt-2 text-xs font-medium text-ink-3">{t('ask.history')}</h2>
      <ul className="flex-1 overflow-y-auto px-2 pb-3">
        {isLoading &&
          [0, 1, 2].map((i) => <li key={i} className="mx-2 my-2 h-8 animate-pulse rounded-[3px] bg-surface-2" />)}
        {data?.length === 0 && <li className="px-2 py-2 text-xs leading-relaxed text-ink-3">{t('ask.noHistory')}</li>}
        {data?.map((c) => (
          <li key={c.id}>
            <Link
              to="/c/$conversationId"
              params={{ conversationId: c.id }}
              className={`block rounded-[4px] px-2 py-1.5 ${c.id === activeId ? 'bg-surface-2 text-ink' : 'text-ink-2 hover:bg-surface-2/60'}`}
            >
              <span className="line-clamp-2 text-[13px] leading-snug">{c.title}</span>
              <span className="font-mono text-[10.5px] text-ink-3">{relativeTime(c.last_at)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  )
}
