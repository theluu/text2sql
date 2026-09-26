import { Link } from '@tanstack/react-router'
import { useTranslation } from 'react-i18next'

export function ErrorView({ error }: { error?: unknown }) {
  const { t } = useTranslation()
  return (
    <div role="alert" className="mx-auto max-w-lg px-8 py-16">
      <h1 className="font-display text-2xl font-semibold">{t('errors.title')}</h1>
      {error instanceof Error && <p className="mt-2 font-mono text-xs text-ink-3">{error.message}</p>}
      <button type="button" onClick={() => window.location.reload()} className="mt-4 rounded-[4px] bg-accent px-3 py-2 text-sm font-medium text-accent-ink">
        {t('errors.reload')}
      </button>
    </div>
  )
}

export function NotFoundView() {
  const { t } = useTranslation()
  return (
    <div className="mx-auto max-w-lg px-8 py-16">
      <h1 className="font-display text-2xl font-semibold">{t('errors.notFound')}</h1>
      <Link to="/" className="mt-3 inline-block text-sm text-accent hover:underline">{t('nav.ask')}</Link>
    </div>
  )
}
