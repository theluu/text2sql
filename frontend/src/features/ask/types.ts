export type RunStatus = 'running' | 'answered' | 'pending_review' | 'rejected' | 'failed'

export interface ResultSet {
  columns: string[]
  column_types: string[]
  rows: unknown[][]
  row_count: number
  truncated: boolean
  draft?: boolean
}

export type ChartSpec =
  | { type: 'empty' }
  | { type: 'table' }
  | { type: 'kpi'; value: string }
  | { type: 'line'; x: string; y: string[] }
  | { type: 'bar'; x: string; y: string[]; horizontal?: boolean }

export interface TraceStep {
  step: string
  status: 'start' | 'ok' | 'error' | 'skip'
  duration_ms?: number
  detail?: Record<string, unknown>
}

export interface JudgeView {
  verdict: 'pass' | 'fail' | 'uncertain'
  score: number
  rubric: Record<string, { score: number; reason: string }>
  issues: string[]
  model: string
  same_vendor: boolean
}

export interface RunView {
  id: string
  conversation_id: string | null
  question: string
  rewritten_question: string | null
  lang: string
  status: RunStatus
  decision: 'AUTO_EXECUTE' | 'NEEDS_REVIEW' | 'REJECT' | null
  reasons: { code: string; label: string }[]
  sql: string | null
  explanation: string | null
  summary: string | null
  chart: ChartSpec | null
  result: ResultSet | null
  confidence: number | null
  provider: string | null
  used_fallback: boolean
  code: string | null
  message: string | null
  cost_usd: number
  latency_ms: number | null
  cache_hit: boolean
  created_at: string | null
  judge: JudgeView | null
  review: { id: string; status: string; note: string | null; edited: boolean } | null
  feedback: 'up' | 'down' | null
  trace: TraceStep[]
  suggestions?: string[]
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  last_at: string
}

export interface ConversationDetail {
  id: string
  title: string
  runs: RunView[]
}

/** A question being answered right now: steps arrive one by one over SSE. */
export interface LiveRun {
  question: string
  runId: string | null
  steps: TraceStep[]
  view: RunView | null
  error: string | null
}

export const PIPELINE_STEPS = [
  'input_guard', 'rewrite', 'cache', 'link', 'fewshot', 'generate', 'validate', 'cost', 'execute', 'judge',
  'consistency', 'risk', 'output',
] as const
