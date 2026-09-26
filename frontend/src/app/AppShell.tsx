import { Link, Outlet, useRouter } from '@tanstack/react-router'
import { LogOut } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { BrandMark } from '@/components/BrandMark'
import { LangToggle } from '@/components/LangToggle'
import { ThemeToggle } from '@/components/ThemeToggle'
import { hasRole, useAuth } from '@/features/auth/store'
import { NAV_ITEMS } from './nav'

export function AppShell() {
  const { t } = useTranslation()
  const router = useRouter()
  const user = useAuth((s) => s.user)
  const logout = useAuth((s) => s.logout)

  return (
    <div className="grid min-h-screen grid-cols-1 bg-paper text-ink lg:grid-cols-[240px_1fr]">
      <aside className="flex flex-col border-b border-rule bg-surface lg:border-b-0 lg:border-r">
        <div className="px-5 py-5">
          <BrandMark />
        </div>
        <nav aria-label={t('shell.primaryNav')} className="flex-1 px-3">
          {NAV_ITEMS.filter((item) => hasRole(user, item.minRole)).map((item) => (
            <Link
              key={item.to}
              to={item.to}
              activeOptions={{ exact: item.exact ?? false }}
              className="flex items-center gap-2.5 rounded-[4px] px-2.5 py-2 text-sm text-ink-2 hover:bg-surface-2 hover:text-ink"
              activeProps={{ className: 'bg-surface-2 text-ink font-medium' }}
            >
              <item.icon size={16} aria-hidden />
              {t(item.labelKey)}
            </Link>
          ))}
        </nav>
        {user && (
          <div className="border-t border-rule p-4">
            <p className="truncate text-sm font-medium">{user.name}</p>
            <p className="truncate font-mono text-[11px] text-ink-3">{user.email}</p>
            <div className="mt-3 flex items-center justify-between">
              <span className="rounded-[3px] border border-rule px-1.5 py-0.5 text-[11px] text-ink-2">
                {t(`auth.roles.${user.role}`)}
              </span>
              <button
                type="button"
                onClick={() => {
                  logout()
                  router.history.push('/login')
                }}
                className="flex items-center gap-1.5 text-xs text-ink-2 hover:text-block"
              >
                <LogOut size={13} aria-hidden />
                {t('shell.logout')}
              </button>
            </div>
          </div>
        )}
      </aside>
      <div className="flex min-w-0 flex-col">
        <header className="flex h-14 items-center justify-end gap-2 border-b border-rule px-6">
          <LangToggle />
          <ThemeToggle />
        </header>
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
