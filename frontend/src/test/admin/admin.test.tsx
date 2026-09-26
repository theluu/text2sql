import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { useAuth } from '@/features/auth/store'
import vi_ from '@/i18n/locales/vi.json'
import { json, mockApi, renderApp } from '../utils'

const ADMIN = { id: 'x', email: 'admin@demo.vn', name: 'Lê Thu Hà', role: 'admin' as const }
const RISK = { review_confidence: 0.7, fallback_confidence: 0.8, gray_cost: 500000, max_cost: 50000000, w_self: 0.2, w_judge: 0.5, w_agreement: 0.3 }
const SETTINGS = {
  llm_chain: ['anthropic', 'openai', 'gemini', 'ollama', 'rule_based'],
  chaos: { disabled_providers: [] },
  risk: RISK,
  features: { llm_classifier: true, self_consistency: true, cache: true },
  risk_defaults: RISK,
  providers: [
    { name: 'anthropic', configured: true, model: 'claude-sonnet-5', circuit: 'open' },
    { name: 'openai', configured: true, model: 'gpt-5-mini', circuit: 'closed' },
    { name: 'gemini', configured: false, model: null, circuit: null },
    { name: 'ollama', configured: false, model: null, circuit: null },
  ],
}
const OPS = {
  days: 14,
  totals: { questions: 3, auto_rate: 0.333, fallback_rate: 0.667, cache_hit_rate: 0, failover_rate: 0, latency_p95_ms: 300, cost_usd: 0, pending_reviews: 1, judge_human_agreement: null },
  decisions: [{ day: '2026-09-26', auto: 1, review: 1, reject: 1, failed: 0, fallback: 2, failover: 0 }],
  costs: [],
  guardrails: [{ layer: 'L1', code: 'INJECTION_SUSPECTED', count: 1 }],
  providers: [{ name: 'anthropic', configured: true, model: 'claude-sonnet-5', in_chain: true, chaos: true, circuit: 'open', calls: 5, error_rate: 1, avg_latency_ms: null }],
}

describe('admin and ops', () => {
  beforeEach(() => useAuth.setState({ token: 'tok', user: ADMIN }))

  it('reorders the chain with keyboard buttons, toggles chaos and saves', async () => {
    const fetchMock = mockApi({
      'GET /api/admin/settings': () => json(SETTINGS),
      'GET /api/admin/semantic': () => json({ version: 'v', embedder: 'hash-v1', tables: [], metrics: [], glossary: [] }),
      'PUT /api/admin/settings': (init) => json({ ...SETTINGS, ...JSON.parse(String(init?.body)) }),
      'POST /api/admin/circuits/anthropic/reset': () => json({ state: 'closed' }),
    })
    renderApp('/admin')
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: vi_.admin.moveDown.replace('{{name}}', 'anthropic') }))
    await user.click(screen.getByRole('checkbox', { name: 'openai' }))
    await user.click(screen.getByRole('button', { name: vi_.admin.resetCircuit }))
    await user.click(screen.getByRole('button', { name: vi_.admin.save }))
    await screen.findByText(vi_.admin.saved)
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === 'PUT')
    const body = JSON.parse(String(put?.[1]?.body))
    expect(body.llm_chain).toEqual(['openai', 'anthropic', 'gemini', 'ollama', 'rule_based'])
    expect(body.chaos).toEqual({ disabled_providers: ['openai'] })
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/circuits/anthropic/reset'))).toBe(true)
  })

  it('shows ops KPIs, provider circuit state with a text label, and a table view of charts', async () => {
    mockApi({ 'GET /api/dashboard/ops': () => json(OPS) })
    renderApp('/ops')
    expect(await screen.findByText(vi_.ops.kpi.questions)).toBeInTheDocument()
    const providers = screen.getByRole('heading', { name: vi_.ops.providers }).parentElement!
    expect(within(providers).getByText(vi_.ops.circuit.open)).toBeInTheDocument()
    expect(within(providers).getByText(vi_.ops.chaos)).toBeInTheDocument()
    expect(screen.getByText('INJECTION_SUSPECTED')).toBeInTheDocument()
    expect(screen.getAllByText(vi_.ops.showTable).length).toBeGreaterThan(0)
  })

  it('keeps analysts out of admin-only pages', async () => {
    useAuth.setState({ token: 'tok', user: { ...ADMIN, role: 'analyst' } })
    mockApi({})
    const router = renderApp('/ops')
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
  })
})
