import { createMemoryHistory, RouterProvider } from '@tanstack/react-router'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createAppRouter } from '@/app/router'
import { useAuth } from '@/features/auth/store'
import vi_ from '@/i18n/locales/vi.json'

const USER = { id: 'u1', email: 'viewer@demo.vn', name: 'Nguyễn Minh Anh', role: 'viewer' as const }

function renderAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }))
  render(<RouterProvider router={router} />)
  return router
}

function stubLogin(status: number, body: unknown) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })))
}

describe('routing & login', () => {
  beforeEach(() => useAuth.setState({ token: null, user: null }))

  it('redirects anonymous users to the login page', async () => {
    const router = renderAt('/')
    expect(await screen.findByRole('heading', { name: vi_.auth.title })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('signs in and lands on the ask page', async () => {
    stubLogin(200, { access_token: 'tok', token_type: 'bearer', user: USER })
    const router = renderAt('/login')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(vi_.auth.email), 'viewer@demo.vn')
    await user.type(screen.getByLabelText(vi_.auth.password), 'demo1234')
    await user.click(screen.getByRole('button', { name: vi_.auth.submit }))
    expect(await screen.findByRole('heading', { name: vi_.ask.title })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
    expect(useAuth.getState().token).toBe('tok')
  })

  it('shows a localized error for invalid credentials', async () => {
    stubLogin(401, { detail: 'invalid_credentials' })
    renderAt('/login')
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(vi_.auth.email), 'viewer@demo.vn')
    await user.type(screen.getByLabelText(vi_.auth.password), 'nope')
    await user.click(screen.getByRole('button', { name: vi_.auth.submit }))
    expect(await screen.findByRole('alert')).toHaveTextContent(vi_.auth.errors.invalid_credentials)
  })

  it('demo account buttons fill the form', async () => {
    renderAt('/login')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: new RegExp(vi_.auth.roles.analyst) }))
    expect(screen.getByLabelText(vi_.auth.email)).toHaveValue('analyst@demo.vn')
    expect(screen.getByLabelText(vi_.auth.password)).toHaveValue('demo1234')
  })

  it.each(['https://evil.example', '//evil.example/x'])('ignores external redirect %s', async (target) => {
    stubLogin(200, { access_token: 'tok', token_type: 'bearer', user: USER })
    const router = renderAt(`/login?redirect=${encodeURIComponent(target)}`)
    const user = userEvent.setup()
    await user.type(await screen.findByLabelText(vi_.auth.email), 'viewer@demo.vn')
    await user.type(screen.getByLabelText(vi_.auth.password), 'demo1234')
    await user.click(screen.getByRole('button', { name: vi_.auth.submit }))
    expect(await screen.findByRole('heading', { name: vi_.ask.title })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/')
  })

  it('shows the signed-in user and signs out back to login', async () => {
    useAuth.setState({ token: 'tok', user: USER })
    const router = renderAt('/')
    expect(await screen.findByText(USER.name)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: vi_.nav.ask })).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: vi_.shell.logout }))
    expect(await screen.findByRole('heading', { name: vi_.auth.title })).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/login')
  })

  it('switches language to English', async () => {
    renderAt('/login')
    await userEvent.setup().click(await screen.findByRole('button', { name: 'EN' }))
    expect(await screen.findByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})
