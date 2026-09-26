import { useRouter, useSearch } from '@tanstack/react-router'
import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { BrandMark } from '@/components/BrandMark'
import { LangToggle } from '@/components/LangToggle'
import { ThemeToggle } from '@/components/ThemeToggle'
import { ApiError } from '@/lib/api'
import { LedgerPreview } from './LedgerPreview'
import { type Role, useAuth } from './store'

const DEMO_ACCOUNTS: { role: Role; email: string }[] = [
  { role: 'viewer', email: 'viewer@demo.vn' },
  { role: 'analyst', email: 'analyst@demo.vn' },
  { role: 'admin', email: 'admin@demo.vn' },
]
const DEMO_PASSWORD = 'demo1234'

export function LoginPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const { redirect } = useSearch({ from: '/login' })
  const login = useAuth((s) => s.login)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(null)
    try {
      await login(email, password)
      router.history.push(redirect ?? '/')
    } catch (err) {
      setError(
        err instanceof ApiError && err.code === 'invalid_credentials'
          ? t('auth.errors.invalid_credentials')
          : t('auth.errors.generic'),
      )
    } finally {
      setPending(false)
    }
  }

  const field =
    'mt-1.5 w-full rounded-[4px] border border-rule bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus:border-accent focus:outline-none'

  return (
    <div className="grid min-h-screen bg-paper lg:grid-cols-[1.15fr_1fr]">
      <aside className="relative hidden flex-col justify-between overflow-hidden bg-[#14161A] p-12 text-[#ECEAE4] lg:flex">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.06]"
          style={{
            backgroundImage:
              'linear-gradient(#ECEAE4 1px, transparent 1px), linear-gradient(90deg, #ECEAE4 1px, transparent 1px)',
            backgroundSize: '32px 32px',
          }}
        />
        <BrandMark inverted />
        <div className="relative max-w-lg">
          <p className="font-display text-[40px] font-semibold leading-[1.05] tracking-tight">{t('brand.tagline')}</p>
          <div className="mt-10 rounded-[6px] border border-[#2C3037] bg-[#1B1E23]/80 p-5">
            <LedgerPreview />
          </div>
        </div>
        <p className="relative max-w-md text-sm leading-relaxed text-[#A9ADB6]">{t('brand.pillars')}</p>
      </aside>

      <main className="flex flex-col px-6 py-6 sm:px-12">
        <div className="flex items-center justify-between lg:justify-end">
          <span className="lg:hidden">
            <BrandMark />
          </span>
          <div className="flex items-center gap-2">
            <LangToggle />
            <ThemeToggle />
          </div>
        </div>

        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-12">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">{t('auth.title')}</h1>
          <p className="mt-2 text-sm text-ink-2">{t('auth.subtitle')}</p>

          <form className="mt-8 space-y-4" onSubmit={onSubmit} noValidate>
            <label className="block text-sm font-medium text-ink-2">
              {t('auth.email')}
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value)
                  setError(null)
                }}
                className={field}
              />
            </label>
            <label className="block text-sm font-medium text-ink-2">
              {t('auth.password')}
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                  setError(null)
                }}
                className={field}
              />
            </label>
            {error && (
              <p role="alert" className="rounded-[4px] border border-block/40 bg-block/10 px-3 py-2 text-sm text-block">
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={pending}
              className="w-full rounded-[4px] bg-accent py-2.5 text-sm font-medium text-accent-ink transition-opacity disabled:opacity-60"
            >
              {pending ? t('auth.submitting') : t('auth.submit')}
            </button>
          </form>

          <section className="mt-10">
            <h2 className="text-sm font-medium text-ink-2">{t('auth.demo')}</h2>
            <ul className="mt-3 divide-y divide-rule overflow-hidden rounded-[4px] border border-rule">
              {DEMO_ACCOUNTS.map((account) => (
                <li key={account.role}>
                  <button
                    type="button"
                    onClick={() => {
                      setEmail(account.email)
                      setPassword(DEMO_PASSWORD)
                      setError(null)
                    }}
                    className="flex w-full items-center justify-between bg-surface px-3 py-2.5 text-left hover:bg-surface-2"
                  >
                    <span className="text-sm text-ink">{t(`auth.roles.${account.role}`)}</span>
                    <span className="font-mono text-xs text-ink-3">{account.email}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </main>
    </div>
  )
}
