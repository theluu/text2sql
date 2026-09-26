import { Check, Copy } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export function SqlBlock({ sql, explanation, open = false }: { sql: string; explanation?: string | null; open?: boolean }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  return (
    <details open={open} className="group rounded-[4px] border border-rule bg-surface">
      <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs text-ink-2 hover:text-ink">
        <span className="font-medium">{t('ask.sql')}</span>
        <span className="font-mono text-ink-3 group-open:hidden">{sql.slice(0, 64)}…</span>
      </summary>
      <div className="border-t border-rule">
        {explanation && <p className="px-3 pt-2 text-[13px] text-ink-2">{explanation}</p>}
        <div className="relative">
          <pre className="overflow-x-auto whitespace-pre-wrap break-words px-3 py-2 font-mono text-[12px] leading-relaxed text-ink">{sql}</pre>
          <button
            type="button"
            onClick={() => {
              void navigator.clipboard?.writeText(sql)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}
            className="absolute right-2 top-2 flex items-center gap-1 rounded-[3px] border border-rule bg-surface px-1.5 py-0.5 text-[11px] text-ink-2 hover:text-ink"
          >
            {copied ? <Check size={12} /> : <Copy size={12} />}
            {copied ? t('ask.copied') : t('ask.copy')}
          </button>
        </div>
      </div>
    </details>
  )
}
