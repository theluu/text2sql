import { useQuery } from '@tanstack/react-query'
import type { ResultSet, RunView } from '@/features/ask/types'
import { apiFetch } from '@/lib/api'

export interface QueueItem {
  id: string
  run_id: string
  question: string
  lang: string
  asker: { name: string; role: string }
  reasons: string[]
  status: string
  priority: number
  assignee: string | null
  confidence: number | null
  provider: string | null
  created_at: string
  resolved_at: string | null
}

export interface ReviewDetail {
  id: string
  status: string
  reasons: string[]
  original_sql: string | null
  final_sql: string | null
  note: string | null
  add_to_golden: boolean
  created_at: string
  resolved_at: string | null
  asker: { name: string; email: string; role: string }
  run: RunView
}

export interface DryRunResult {
  ok: boolean
  sql: string | null
  code: string | null
  message: string | null
  result: ResultSet | null
  cost: number | null
  pii_columns: string[]
  masked: string[]
}

export const reviewKeys = {
  queue: (status: string, reason: string) => ['review', 'queue', status, reason] as const,
  detail: (id: string) => ['review', 'detail', id] as const,
  count: ['review', 'count'] as const,
}

export function useReviewQueue(status: string, reason: string) {
  const params = new URLSearchParams({ status })
  if (reason) params.set('reason', reason)
  return useQuery({
    queryKey: reviewKeys.queue(status, reason),
    queryFn: () => apiFetch<{ items: QueueItem[]; pending: number }>(`/review?${params}`),
    refetchInterval: 15_000,
  })
}

export function useReviewDetail(id: string) {
  return useQuery({ queryKey: reviewKeys.detail(id), queryFn: () => apiFetch<ReviewDetail>(`/review/${id}`) })
}

export function usePendingCount(enabled: boolean) {
  return useQuery({
    queryKey: reviewKeys.count,
    queryFn: () => apiFetch<{ pending: number }>('/review/count'),
    enabled,
    refetchInterval: 30_000,
  })
}

const post = <T,>(path: string, body: unknown = {}) =>
  apiFetch<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const reviewApi = {
  claim: (id: string) => post<{ status: string }>(`/review/${id}/claim`),
  dryRun: (id: string, sql: string) => post<DryRunResult>(`/review/${id}/dry-run`, { sql }),
  approve: (id: string, body: { note?: string; add_to_golden: boolean }) => post<{ status: string }>(`/review/${id}/approve`, body),
  edit: (id: string, body: { sql: string; note?: string; add_to_golden: boolean }) => post<{ status: string }>(`/review/${id}/edit`, body),
  reject: (id: string, note: string) => post<{ status: string }>(`/review/${id}/reject`, { note }),
  returnToAsker: (id: string, note: string) => post<{ status: string }>(`/review/${id}/return`, { note }),
}
