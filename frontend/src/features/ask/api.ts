import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api'
import { postStream, type SseEvent } from '@/lib/sse'
import type { ConversationDetail, ConversationSummary } from './types'

export const conversationKeys = {
  all: ['conversations'] as const,
  detail: (id: string) => ['conversations', id] as const,
}

export function useConversations() {
  return useQuery({ queryKey: conversationKeys.all, queryFn: () => apiFetch<ConversationSummary[]>('/conversations') })
}

export function useConversation(id: string | undefined) {
  return useQuery({
    queryKey: conversationKeys.detail(id ?? 'none'),
    queryFn: () => apiFetch<ConversationDetail>(`/conversations/${id}`),
    enabled: Boolean(id),
    // Poll while any answer awaits review (SSE notifications are the fast path).
    refetchInterval: (query) =>
      query.state.data?.runs.some((r) => r.status === 'pending_review') ? 15_000 : false,
  })
}

export function askQuestion(
  question: string,
  conversationId: string | undefined,
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal,
) {
  return postStream('/query', { question, conversation_id: conversationId }, onEvent, signal)
}

export function sendFeedback(runId: string, rating: 'up' | 'down', comment?: string) {
  return apiFetch<{ ok: boolean }>(`/query-runs/${runId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating, comment }),
  })
}
