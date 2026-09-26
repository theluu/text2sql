import { ArrowUp, Square } from 'lucide-react'
import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

export function Composer({
  onSubmit,
  onStop,
  busy,
  autoFocus = false,
}: {
  onSubmit: (question: string) => void
  onStop: () => void
  busy: boolean
  autoFocus?: boolean
}) {
  const { t } = useTranslation()
  const [value, setValue] = useState('')
  const ref = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (autoFocus) ref.current?.focus()
  }, [autoFocus])

  function submit(event?: FormEvent) {
    event?.preventDefault()
    const question = value.trim()
    if (!question || busy) return
    onSubmit(question)
    setValue('')
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit()
    }
  }

  return (
    <form onSubmit={submit} className="flex items-end gap-2 rounded-[6px] border border-rule bg-surface p-2 focus-within:border-accent">
      <label className="sr-only" htmlFor="question">
        {t('ask.placeholder')}
      </label>
      <textarea
        id="question"
        ref={ref}
        rows={1}
        value={value}
        maxLength={500}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={t('ask.placeholder')}
        className="max-h-40 min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] text-ink placeholder:text-ink-3 focus:outline-none focus-visible:outline-none"
        style={{ fieldSizing: 'content' } as React.CSSProperties}
      />
      {busy ? (
        <button type="button" onClick={onStop} aria-label={t('ask.stop')} className="grid h-9 w-9 place-items-center rounded-[4px] border border-rule text-ink-2 hover:text-ink">
          <Square size={14} />
        </button>
      ) : (
        <button type="submit" aria-label={t('ask.send')} disabled={!value.trim()} className="grid h-9 w-9 place-items-center rounded-[4px] bg-accent text-accent-ink disabled:opacity-40">
          <ArrowUp size={16} />
        </button>
      )}
    </form>
  )
}
