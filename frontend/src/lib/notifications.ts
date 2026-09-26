import { useQueryClient } from '@tanstack/react-query'
import { useRouter } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useToasts } from '@/components/Toasts'
import { useAuth } from '@/features/auth/store'
import { streamSse } from './sse'

interface ReviewResolved {
  type: 'review_resolved'
  run_id: string
  conversation_id: string
  status: string
  question: string
}

/** Keeps one notification stream open while signed in; reconnects with backoff. */
export function useNotifications() {
  const token = useAuth((s) => s.token)
  const client = useQueryClient()
  const router = useRouter()
  const push = useToasts((s) => s.push)
  const { t } = useTranslation()

  useEffect(() => {
    if (!token) return
    const controller = new AbortController()
    let delay = 2000
    let timer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      streamSse(
        '/notifications/stream',
        { method: 'GET' },
        ({ event, data }) => {
          delay = 2000
          if (event !== 'review_resolved') return
          const payload = data as ReviewResolved
          void client.invalidateQueries({ queryKey: ['conversations'] })
          const tone = payload.status === 'answered' ? 'ok' : payload.status === 'rejected' ? 'block' : 'warn'
          push({
            title: t(`notifications.${payload.status}`, t('notifications.generic')),
            body: payload.question,
            tone,
            action: {
              label: t('notifications.open'),
              onClick: () =>
                void router.navigate({ to: '/c/$conversationId', params: { conversationId: payload.conversation_id } }),
            },
          })
        },
        controller.signal,
      )
        .catch(() => undefined)
        .finally(() => {
          if (controller.signal.aborted) return
          timer = setTimeout(connect, delay)
          delay = Math.min(delay * 2, 60_000)
        })
    }
    connect()
    return () => {
      controller.abort()
      if (timer) clearTimeout(timer)
    }
  }, [token, client, router, push, t])
}
