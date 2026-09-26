import { useTranslation } from 'react-i18next'
import { LANGS } from '@/i18n'

export function LangToggle() {
  const { t, i18n } = useTranslation()
  return (
    <div role="group" aria-label={t('shell.language')} className="flex rounded-[4px] border border-rule p-0.5">
      {LANGS.map((lang) => {
        const active = i18n.resolvedLanguage === lang
        return (
          <button
            key={lang}
            type="button"
            aria-pressed={active}
            onClick={() => void i18n.changeLanguage(lang)}
            className={`rounded-[3px] px-2 py-0.5 font-mono text-[11px] tracking-wider transition-colors ${
              active ? 'bg-ink text-paper' : 'text-ink-3 hover:text-ink'
            }`}
          >
            {lang.toUpperCase()}
          </button>
        )
      })}
    </div>
  )
}
