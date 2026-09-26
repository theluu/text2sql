import { useTranslation } from 'react-i18next'
import { useAuth } from '@/features/auth/store'

export function AskPage() {
  const { t } = useTranslation()
  const user = useAuth((s) => s.user)
  const suggestions = t('ask.suggestions', { returnObjects: true }) as unknown as string[]

  return (
    <section className="mx-auto flex max-w-3xl flex-col px-6 py-16">
      <p className="text-sm text-ink-2">
        {t('ask.eyebrow', { name: user?.name ?? '' })}
      </p>
      <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight">{t('ask.title')}</h1>
      <p className="mt-3 max-w-xl text-ink-2">{t('ask.subtitle')}</p>
      <ul className="mt-10 grid gap-px overflow-hidden rounded-[6px] border border-rule bg-rule sm:grid-cols-2">
        {suggestions.map((question) => (
          <li key={question} className="bg-surface p-4 text-sm leading-relaxed">
            {question}
          </li>
        ))}
      </ul>
    </section>
  )
}
