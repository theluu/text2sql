import { Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { currentTheme, setTheme, type Theme } from '@/lib/theme'

export function ThemeToggle() {
  const { t } = useTranslation()
  const [theme, setLocal] = useState<Theme>(currentTheme)
  const next: Theme = theme === 'dark' ? 'light' : 'dark'
  return (
    <button
      type="button"
      aria-label={t(next === 'dark' ? 'shell.theme.toDark' : 'shell.theme.toLight')}
      onClick={() => {
        setTheme(next)
        setLocal(next)
      }}
      className="grid h-7 w-7 place-items-center rounded-[4px] border border-rule text-ink-2 hover:text-ink"
    >
      {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
    </button>
  )
}
