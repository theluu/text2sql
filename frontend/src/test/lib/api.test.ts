import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, configureApi } from '@/lib/api'

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('apiFetch', () => {
  beforeEach(() => configureApi({ getToken: () => null, onUnauthorized: () => {} }))

  it('prefixes /api and attaches bearer token', async () => {
    configureApi({ getToken: () => 'tok', onUnauthorized: () => {} })
    const fetchMock = stubFetch(200, { ok: true })
    await expect(apiFetch('/auth/me')).resolves.toEqual({ ok: true })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/auth/me')
    expect(new Headers(init.headers).get('Authorization')).toBe('Bearer tok')
  })

  it('maps error detail to ApiError.code', async () => {
    stubFetch(401, { detail: 'invalid_credentials' })
    await expect(apiFetch('/auth/login', { method: 'POST' })).rejects.toMatchObject({
      status: 401,
      code: 'invalid_credentials',
    })
  })

  it('falls back to http_<status> when body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('boom', { status: 502 })))
    const error = await apiFetch('/x').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).code).toBe('http_502')
  })

  it('notifies onUnauthorized for 401 on authenticated calls', async () => {
    const onUnauthorized = vi.fn()
    configureApi({ getToken: () => 'expired', onUnauthorized })
    stubFetch(401, { detail: 'not_authenticated' })
    await expect(apiFetch('/auth/me')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})
