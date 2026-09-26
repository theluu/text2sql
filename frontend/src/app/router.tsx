import { createRootRoute, createRoute, createRouter, Outlet, redirect, type RouterHistory } from '@tanstack/react-router'
import { AskPage } from '@/features/ask/AskPage'
import { LoginPage } from '@/features/auth/LoginPage'
import { hasRole, type Role, useAuth } from '@/features/auth/store'
import { ReviewDetailPage } from '@/features/review/ReviewDetailPage'
import { ReviewQueuePage } from '@/features/review/ReviewQueuePage'
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
const conversationRoute = createRoute({ getParentRoute: () => appRoute, path: '/c/$conversationId', component: AskPage })

/** Pages below a role send the user home instead of rendering a 403. */
function requireRole(minimum: Role) {
  return () => {
    if (!hasRole(useAuth.getState().user, minimum)) throw redirect({ to: '/' })
  }
}

const reviewRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/review',
  beforeLoad: requireRole('analyst'),
  component: ReviewQueuePage,
})
const reviewDetailRoute = createRoute({
  getParentRoute: () => appRoute,
  path: '/review/$itemId',
  beforeLoad: requireRole('analyst'),
  component: ReviewDetailPage,
})

const routeTree = rootRoute.addChildren([
  loginRoute,
  appRoute.addChildren([askRoute, conversationRoute, reviewRoute, reviewDetailRoute]),
])

export function createAppRouter(history?: RouterHistory) {
  return createRouter({ routeTree, history, defaultPreload: 'intent' })
}

declare module '@tanstack/react-router' {
  interface Register {
    router: ReturnType<typeof createAppRouter>
  }
}
