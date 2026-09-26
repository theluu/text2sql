import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'

export type RiskSettings = Record<'review_confidence' | 'fallback_confidence' | 'gray_cost' | 'max_cost' | 'w_self' | 'w_judge' | 'w_agreement', number>
export type Features = Record<'llm_classifier' | 'self_consistency' | 'cache', boolean>

export interface AdminSettings {
  llm_chain: string[]
  chaos: { disabled_providers: string[] }
  risk: RiskSettings
  features: Features
  risk_defaults: RiskSettings
  providers: { name: string; configured: boolean; model: string | null; circuit: 'closed' | 'open' | 'half_open' | null }[]
}

export interface SemanticLayer {
  version: string
  embedder: string
  tables: {
    name: string
    vi: string
    en: string
    view_of: string | null
    viewer_via: string | null
    columns: { name: string; type: string; vi: string; en: string; pii: boolean; fk: string | null }[]
  }[]
  metrics: { name: string; vi: string; en: string; sql: string; filter: string | null; tables: string[] }[]
  glossary: { term: string; en: string; maps_to: string }[]
}

export const adminKeys = { settings: ['admin', 'settings'] as const, semantic: ['admin', 'semantic'] as const }

export function useAdminSettings() {
  return useQuery({ queryKey: adminKeys.settings, queryFn: () => apiFetch<AdminSettings>('/admin/settings') })
}

export function useSemantic() {
  return useQuery({ queryKey: adminKeys.semantic, queryFn: () => apiFetch<SemanticLayer>('/admin/semantic'), staleTime: Infinity })
}

export function saveSettings(body: Partial<Pick<AdminSettings, 'llm_chain' | 'chaos' | 'risk' | 'features'>>) {
  return apiFetch<AdminSettings>('/admin/settings', { method: 'PUT', body: JSON.stringify(body) })
}

export function resetCircuit(provider: string) {
  return apiFetch<{ state: string }>(`/admin/circuits/${provider}/reset`, { method: 'POST' })
}
