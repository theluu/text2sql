import { createRootRoute, createRoute, createRouter, Outlet, redirect, type RouterHistory } from '@tanstack/react-router'
import { AskPage } from '@/features/ask/AskPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { useAuth } from '@/features/auth/store'
import { AppShell } from './AppShell'

/** Only same-origin absolute paths are allowed as post-login destinations. */
export function safeRedirect(value: unknown): string | undefined {
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') ? value : undefined
}

const rootRoute = createRootRoute({ component: Outlet })

const loginRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/login',
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => ({
    redirect: safeRedirect(search.redirect),
  }),
  beforeLoad: () => {
    if (useAuth.getState().token) throw redirect({ to: '/' })
  },
  component: LoginPage,
})

const appRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: '_app',
  beforeLoad: ({ location }) => {
    if (!useAuth.getState().token) {
      throw redirect({ to: '/login', search: { redirect: location.href } })
    }
  },
  component: AppShell,
})

const askRoute = createRoute({ getParentRoute: () => appRoute, path: '/', component: AskPage })

const routeTree = rootRoute.addChildren([loginRoute, appRoute.addChildren([askRoute])])

export function createAppRouter(history?: RouterHistory) {
  return createRouter({ routeTree, history, defaultPreload: 'intent' })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
