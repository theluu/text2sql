import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it } from 'vitest'
import { useAuth } from '@/features/auth/store'
import vi_ from '@/i18n/locales/vi.json'
import { json, mockApi, renderApp } from '../utils'

const ANALYST = { id: 'a1', email: 'analyst@demo.vn', name: 'Trần Quốc Bảo', role: 'analyst' as const }
const SUMMARY = {
  cases: 30, ex: 0.762, esm: 0.29, behavior_accuracy: 0.833, guardrail_recall: 1, guardrail_precision: 1,
  adversarial_leaks: [], judge_precision: null, judge_recall: null, judge_kappa: null, linking_recall: 1,
  latency_p50_ms: 80, latency_p95_ms: 284, cost_per_query_usd: 0, failover_rate: 0, fallback_rate: 0.63,
  by_difficulty: { hard: { n: 3, ex: 0, behavior: 0.33 }, easy: { n: 14, ex: 1, behavior: 1 } },
  by_tag: { join3: { n: 7, ex: 0.71, behavior: 0.86 } },
}
const RUN = {
  id: 'r1', suite: 'smoke', mode: 'chain', status: 'done', total: 30, done: 30, git_sha: 'abcdef1234',
  prompt_version: 'v1', model_chain: ['rule_based'], started_at: new Date().toISOString(),
  finished_at: new Date().toISOString(), summary: SUMMARY,
}
const RESULT = {
  case_id: 'c1', key: 'h04', question: 'Doanh thu lũy kế theo tháng năm 2025', lang: 'vi', role: 'analyst',
  difficulty: 'hard', tags: ['window_fn'], expected: 'answer', behavior: 'fail', ex: false, esm: false, judge: null,
  guardrail_code: 'NO_FALLBACK_MATCH', provider: null, fallback: false, latency_ms: 23, cost_usd: 0,
  gold_sql: 'SELECT 1', predicted_sql: null, error: null, linked_tables: [],
}

describe('evaluation pages', () => {
  beforeEach(() => useAuth.setState({ token: 'tok', user: ANALYST }))

  it('starts a run with the chosen suite and mode', async () => {
    const fetchMock = mockApi({
      'GET /api/eval/runs': () => json([RUN]),
      'GET /api/eval/modes': () => json({ suites: ['smoke', 'full'], modes: ['chain', 'rule_based', 'provider=anthropic'] }),
      'POST /api/eval/runs': () => json({ ...RUN, id: 'r2', status: 'queued', done: 0, summary: null }, 202),
    })
    renderApp('/eval')
    expect(await screen.findByText('76.2%')).toBeInTheDocument()
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText(vi_.eval.mode), 'rule_based')
    await user.click(screen.getByRole('button', { name: vi_.eval.run }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([u, i]) => String(u) === '/api/eval/runs' && i?.method === 'POST')).toBe(true))
    const post = fetchMock.mock.calls.find(([u, i]) => String(u) === '/api/eval/runs' && i?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ suite: 'smoke', mode: 'rule_based' })
  })

  it('shows KPIs, ordered breakdowns and expandable failing cases', async () => {
    mockApi({ 'GET /api/eval/runs/r1': () => json({ ...RUN, results: [RESULT] }) })
    renderApp('/eval/r1')
    expect(await screen.findByText(vi_.eval.kpi.ex)).toBeInTheDocument()
    expect(screen.getByText(vi_.eval.kpi.guardrail).nextElementSibling).toHaveTextContent('100%')
    const groups = screen.getAllByRole('cell').map((c) => c.textContent)
    expect(groups.indexOf(vi_.eval.difficulty.easy)).toBeLessThan(groups.indexOf(vi_.eval.difficulty.hard))
    await userEvent.setup().click(screen.getByText(RESULT.question))
    expect(await screen.findByText(vi_.eval.gold)).toBeInTheDocument()
    expect(screen.getByText(vi_.eval.none)).toBeInTheDocument()
  })

  it('compares two runs', async () => {
    mockApi({
      'GET /api/eval/compare': () =>
        json({ a: RUN, b: { ...RUN, id: 'r2', summary: { ...SUMMARY, ex: 0.8 } }, unchanged: 29,
               improved: [{ key: 'h04', question: RESULT.question, before: 'fail', after: 'answer', ex_before: false, ex_after: true }],
               regressed: [] }),
    })
    renderApp('/eval/compare?a=r1&b=r2')
    expect(await screen.findByText(vi_.eval.improved.replace('{{count}}', '1'))).toBeInTheDocument()
    expect(screen.getByText('+3.8%')).toBeInTheDocument()
  })
})
