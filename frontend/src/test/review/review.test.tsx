import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuth } from '@/features/auth/store'
import en from '@/i18n/locales/en.json'
import vi_ from '@/i18n/locales/vi.json'
import { json, mockApi, renderApp } from '../utils'

vi.mock('@/features/review/SqlDiffEditor', () => ({
  default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea aria-label="sql-editor" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}))

const ANALYST = { id: 'a1', email: 'analyst@demo.vn', name: 'Trần Quốc Bảo', role: 'analyst' as const }
const ITEM = {
  id: 'i1', run_id: 'r1', question: 'Email khách hàng platinum', lang: 'vi', asker: { name: 'Nguyễn Minh Anh', role: 'viewer' },
  reasons: ['PII_ACCESS'], status: 'open', priority: 3.2, assignee: null, confidence: 0.9, provider: 'anthropic',
  created_at: new Date().toISOString(), resolved_at: null,
}
const DETAIL = {
  id: 'i1', status: 'claimed', reasons: ['PII_ACCESS'], original_sql: 'SELECT email FROM v_customers_masked', final_sql: null,
  note: null, add_to_golden: false, created_at: ITEM.created_at, resolved_at: null,
  asker: { name: 'Nguyễn Minh Anh', email: 'viewer@demo.vn', role: 'viewer' },
  run: {
    id: 'r1', conversation_id: 'c1', question: ITEM.question, rewritten_question: null, lang: 'vi', status: 'pending_review',
    decision: 'NEEDS_REVIEW', reasons: [], sql: 'SELECT email FROM v_customers_masked', explanation: null, summary: null,
    chart: null, result: null, confidence: 0.9, provider: 'anthropic', used_fallback: false, code: null, message: null,
    cost_usd: 0, latency_ms: 10, cache_hit: false, created_at: null, judge: null, review: null, feedback: null, trace: [],
  },
}

describe('review queue', () => {
  beforeEach(() => useAuth.setState({ token: 'tok', user: ANALYST }))

  it('lists items and opens the detail', async () => {
    mockApi({
      'GET /api/review?': () => json({ items: [ITEM], pending: 1 }),
      'GET /api/review/count': () => json({ pending: 1 }),
      'GET /api/review/i1': () => json(DETAIL),
    })
    const router = renderApp('/review')
    const link = await screen.findByRole('link', { name: ITEM.question })
    expect(screen.getAllByText(vi_.reasons.PII_ACCESS).length).toBe(2) // filter option + chip
    await userEvent.setup().click(link)
    await waitFor(() => expect(router.state.location.pathname).toBe('/review/i1'))
  })

  it('approves with the A shortcut and requires a note to reject', async () => {
    const fetchMock = mockApi({
      'GET /api/review/i1': () => json(DETAIL),
      'POST /api/review/i1/approve': () => json({ status: 'approved' }),
    })
    renderApp('/review/i1')
    await screen.findByRole('button', { name: vi_.review.approve })

    await userEvent.setup().click(screen.getByRole('button', { name: vi_.review.reject }))
    expect(await screen.findByRole('alert')).toHaveTextContent(vi_.review.noteRequired)
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/reject'))).toBe(false)

    fireEvent.keyDown(document.body, { key: 'a' })
    expect(await screen.findByText(vi_.review.resolved.replace('{{status}}', vi_.review.statuses.approved))).toBeInTheDocument()
    const approve = fetchMock.mock.calls.find(([u]) => String(u).endsWith('/approve'))
    expect(JSON.parse(String(approve?.[1]?.body))).toEqual({ add_to_golden: false })
  })

  it('switches to edit-and-approve after the SQL changes and shows dry-run errors', async () => {
    const fetchMock = mockApi({
      'GET /api/review/i1': () => json(DETAIL),
      'POST /api/review/i1/dry-run': () =>
        json({ ok: false, sql: null, code: 'TABLE_NOT_ALLOWED', message: 'table customers is not allowed for viewer', result: null, cost: null, pii_columns: [], masked: [] }),
      'POST /api/review/i1/edit': () => json({ status: 'edited' }),
    })
    renderApp('/review/i1')
    const editor = await screen.findByLabelText('sql-editor')
    const user = userEvent.setup()
    expect(screen.getByRole('button', { name: vi_.review.edit })).toBeDisabled()
    await user.clear(editor)
    await user.type(editor, 'SELECT email FROM customers')
    await user.click(screen.getByRole('button', { name: vi_.review.dryRun }))
    expect(await screen.findByText(/TABLE_NOT_ALLOWED/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: vi_.review.approve })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: vi_.review.edit }))
    await screen.findByText(vi_.review.resolved.replace('{{status}}', vi_.review.statuses.edited))
    const body = JSON.parse(String(fetchMock.mock.calls.find(([u]) => String(u).endsWith('/edit'))?.[1]?.body))
    expect(body.sql).toBe('SELECT email FROM customers')
  })

  it('keeps viewers out of the review pages', async () => {
    useAuth.setState({ token: 'tok', user: { ...ANALYST, role: 'viewer' } })
    mockApi({})
    const router = renderApp('/review')
    await waitFor(() => expect(router.state.location.pathname).toBe('/'))
    expect(screen.queryByRole('link', { name: en.nav.review })).not.toBeInTheDocument()
  })
})
