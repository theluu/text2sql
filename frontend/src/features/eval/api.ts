import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface Breakdown {
  n: number
  ex: number | null
  behavior: number | null
}

export interface EvalSummary {
  cases: number
  ex: number | null
  esm: number | null
  behavior_accuracy: number | null
  guardrail_recall: number | null
  guardrail_precision: number | null
  adversarial_leaks: string[]
  judge_precision: number | null
  judge_recall: number | null
  judge_kappa: number | null
  linking_recall: number | null
  latency_p50_ms: number
  latency_p95_ms: number
  cost_per_query_usd: number
  failover_rate: number | null
  fallback_rate: number | null
  by_difficulty: Record<string, Breakdown>
  by_tag: Record<string, Breakdown>
  error?: string
}

export interface EvalRun {
  id: string
  suite: string
  mode: string
  status: 'queued' | 'running' | 'done' | 'failed'
  total: number
  done: number | null
  git_sha: string | null
  prompt_version: string
  model_chain: string[]
  started_at: string
  finished_at: string | null
  summary: EvalSummary | null
}

export interface EvalCaseResult {
  case_id: string
  key: string
  question: string
  lang: string
  role: string
  difficulty: string
  tags: string[]
  expected: string
  behavior: string
  ex: boolean | null
  esm: boolean | null
  judge: string | null
  guardrail_code: string | null
  provider: string | null
  fallback: boolean
  latency_ms: number
  cost_usd: number
  gold_sql: string | null
  predicted_sql: string | null
  error: string | null
  linked_tables: string[]
}

export interface CompareEntry {
  key: string
  question: string
  before: string
  after: string
  ex_before: boolean | null
  ex_after: boolean | null
}

export interface Comparison {
  a: EvalRun
  b: EvalRun
  improved: CompareEntry[]
  regressed: CompareEntry[]
  unchanged: number
}

export const evalKeys = {
  runs: ['eval', 'runs'] as const,
  run: (id: string) => ['eval', 'run', id] as const,
  modes: ['eval', 'modes'] as const,
  compare: (a: string, b: string) => ['eval', 'compare', a, b] as const,
}

export function useEvalRuns() {
  return useQuery({
    queryKey: evalKeys.runs,
    queryFn: () => apiFetch<EvalRun[]>('/eval/runs'),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'running' || r.status === 'queued') ? 3000 : false),
  })
}

export function useEvalRun(id: string) {
  return useQuery({
    queryKey: evalKeys.run(id),
    queryFn: () => apiFetch<EvalRun & { results: EvalCaseResult[] }>(`/eval/runs/${id}`),
    refetchInterval: (q) => (q.state.data && ['running', 'queued'].includes(q.state.data.status) ? 2000 : false),
  })
}

export function useEvalModes() {
  return useQuery({ queryKey: evalKeys.modes, queryFn: () => apiFetch<{ suites: string[]; modes: string[] }>('/eval/modes') })
}

export function useComparison(a: string, b: string) {
  return useQuery({
    queryKey: evalKeys.compare(a, b),
    queryFn: () => apiFetch<Comparison>(`/eval/compare?a=${a}&b=${b}`),
    enabled: Boolean(a && b),
  })
}

export function startRun(suite: string, mode: string) {
  return apiFetch<EvalRun>('/eval/runs', { method: 'POST', body: JSON.stringify({ suite, mode }) })
}
