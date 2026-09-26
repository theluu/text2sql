import { beforeEach, describe, expect, it, vi } from 'vitest'
import { hasRole, useAuth } from '@/features/auth/store'

const USER = { id: 'u1', email: 'analyst@demo.vn', name: 'Trần Quốc Bảo', role: 'analyst' as const }

describe('useAuth', () => {
  beforeEach(() => useAuth.setState({ token: null, user: null }))

  it('stores token and user after successful login', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ access_token: 'tok', token_type: 'bearer', user: USER }), { status: 200 }),
    ))
    await useAuth.getState().login('analyst@demo.vn', 'demo1234')
    expect(useAuth.getState()).toMatchObject({ token: 'tok', user: USER })
  })

  it('leaves state untouched when login fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ detail: 'invalid_credentials' }), { status: 401 }),
    ))
    await expect(useAuth.getState().login('x@demo.vn', 'bad')).rejects.toMatchObject({ code: 'invalid_credentials' })
    expect(useAuth.getState().token).toBeNull()
  })

  it('logout clears the session', () => {
    useAuth.setState({ token: 'tok', user: USER })
    useAuth.getState().logout()
    expect(useAuth.getState()).toMatchObject({ token: null, user: null })
  })

  it('hasRole follows viewer < analyst < admin', () => {
    expect(hasRole(USER, 'viewer')).toBe(true)
    expect(hasRole(USER, 'analyst')).toBe(true)
    expect(hasRole(USER, 'admin')).toBe(false)
    expect(hasRole(null, 'viewer')).toBe(false)
  })
})
