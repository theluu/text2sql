import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export interface ProviderHealth {
  name: string
  configured: boolean
  model: string | null
  in_chain: boolean
  chaos: boolean
  circuit: 'closed' | 'open' | 'half_open' | null
  calls: number
  error_rate: number | null
  avg_latency_ms: number | null
}

export interface OpsData {
  days: number
  totals: {
    questions: number
    auto_rate: number | null
    fallback_rate: number | null
    cache_hit_rate: number | null
    failover_rate: number | null
    latency_p95_ms: number | null
    cost_usd: number
    pending_reviews: number
    judge_human_agreement: number | null
  }
  decisions: { day: string; auto: number; review: number; reject: number; failed: number; fallback: number; failover: number }[]
  costs: { day: string; cost_usd: number; calls: number; tokens: number }[]
  guardrails: { layer: string; code: string; count: number }[]
  providers: ProviderHealth[]
}

export function useOps(days: number) {
  return useQuery({
    queryKey: ['ops', days],
    queryFn: () => apiFetch<OpsData>(`/dashboard/ops?days=${days}`),
    refetchInterval: 30_000,
  })
}
