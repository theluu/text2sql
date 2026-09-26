import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from '@tanstack/react-router'
import { PanelRight } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/features/auth/store'
import { askQuestion, conversationKeys, useConversation } from './api'
import { Composer } from './Composer'
import { ConversationList } from './ConversationList'
import { RunCard } from './RunCard'
import { TracePanel } from './TracePanel'
import type { LiveRun, RunView, TraceStep } from './types'

export function AskPage() {
  const { t } = useTranslation()
  const user = useAuth((s) => s.user)
  const params = useParams({ strict: false }) as { conversationId?: string }
  const conversationId = params.conversationId
  const navigate = useNavigate()
  const client = useQueryClient()
  const { data, isError } = useConversation(conversationId)
  const [live, setLive] = useState<LiveRun | null>(null)
  const [traceOf, setTraceOf] = useState<string | 'live' | null>(null)
  const [traceOpen, setTraceOpen] = useState(true)
  const abort = useRef<AbortController | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const runs: RunView[] = data?.id === conversationId ? data?.runs ?? [] : []
  const visibleRuns = live?.view ? runs.filter((r) => r.id !== live.view?.id) : runs

  useEffect(() => {
    // Leaving a conversation drops any finished live run; a running one keeps streaming.
    setLive((current) => (current && current.view ? null : current))
    setTraceOf(null)
  }, [conversationId])

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [live?.steps.length, live?.view, runs.length])

  const ask = useCallback(
    async (question: string) => {
      abort.current?.abort()
      const controller = new AbortController()
      abort.current = controller
      setLive({ question, runId: null, steps: [], view: null, error: null })
      setTraceOf('live')
      let targetConversation = conversationId
      try {
        await askQuestion(
          question,
          conversationId,
          ({ event, data: payload }) => {
            if (event === 'meta') {
              const meta = payload as { run_id: string; conversation_id: string }
              targetConversation = meta.conversation_id
              setLive((l) => (l ? { ...l, runId: meta.run_id } : l))
            } else if (event === 'step') {
              const step = payload as TraceStep
              setLive((l) => (l ? { ...l, steps: [...l.steps, step] } : l))
            } else if (event === 'result') {
              setLive((l) => (l ? { ...l, view: payload as RunView } : l))
            } else if (event === 'error') {
              setLive((l) => (l ? { ...l, error: t('ask.streamError') } : l))
            }
          },
          controller.signal,
        )
      } catch (error) {
        if (!controller.signal.aborted) setLive((l) => (l ? { ...l, error: t('ask.streamError') } : l))
        void error
      } finally {
        await client.invalidateQueries({ queryKey: conversationKeys.all })
        if (targetConversation && targetConversation !== conversationId) {
          void navigate({ to: '/c/$conversationId', params: { conversationId: targetConversation } })
        }
      }
    },
    [client, conversationId, navigate, t],
  )

  const stop = () => {
    abort.current?.abort()
    setLive(null)
  }

  const liveTrace = live?.view?.trace ?? live?.steps ?? []
  const selected: RunView | null =
    traceOf === 'live' ? live?.view ?? null : runs.find((r) => r.id === traceOf) ?? runs[runs.length - 1] ?? null
  const panelTrace = traceOf === 'live' ? liveTrace : selected?.trace ?? []
  const empty = !conversationId && !live
  const suggestions = t('ask.suggestions', { returnObjects: true }) as unknown as string[]

  return (
    <div className="grid h-[calc(100vh-3.5rem)] grid-cols-1 md:grid-cols-[248px_1fr] xl:grid-cols-[248px_1fr_auto]">
      <div className="hidden min-h-0 md:block">
        <ConversationList activeId={conversationId} />
      </div>

      <section className="flex min-h-0 min-w-0 flex-col">
        <div className="flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[860px] px-6">
            {empty ? (
              <div className="py-16">
                <p className="text-sm text-ink-2">{t('ask.eyebrow', { name: user?.name ?? '' })}</p>
                <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight">{t('ask.title')}</h1>
                <p className="mt-3 max-w-xl text-ink-2">{t('ask.subtitle')}</p>
                <ul className="mt-10 grid gap-px overflow-hidden rounded-[6px] border border-rule bg-rule sm:grid-cols-2">
                  {suggestions.map((question) => (
                    <li key={question}>
                      <button type="button" onClick={() => void ask(question)} className="h-full w-full bg-surface p-4 text-left text-sm leading-relaxed hover:bg-surface-2">
                        {question}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="py-4">
                {isError && <p className="py-6 text-sm text-block">{t('ask.loadError')}</p>}
                {visibleRuns.map((run) => (
                  <RunCard
                    key={run.id}
                    run={run}
                    question={run.question}
                    onAsk={(q) => void ask(q)}
                    onOpenTrace={() => {
                      setTraceOf(run.id)
                      setTraceOpen(true)
                    }}
                  />
                ))}
                {live && (
                  <RunCard
                    run={live.view}
                    question={live.question}
                    liveSteps={live.steps}
                    onAsk={(q) => void ask(q)}
                    onOpenTrace={() => {
                      setTraceOf('live')
                      setTraceOpen(true)
                    }}
                  />
                )}
                {live?.error && (
                  <p role="alert" className="py-2 text-sm text-block">
                    {live.error}
                  </p>
                )}
              </div>
            )}
            <div ref={bottom} />
          </div>
        </div>
        <div className="border-t border-rule bg-paper px-6 py-3">
          <div className="mx-auto flex max-w-[860px] items-end gap-2">
            <div className="flex-1">
              <Composer onSubmit={(q) => void ask(q)} onStop={stop} busy={Boolean(live && !live.view && !live.error)} autoFocus />
            </div>
            {!traceOpen && (
              <button type="button" onClick={() => setTraceOpen(true)} aria-label={t('ask.showTrace')} className="hidden h-11 w-11 place-items-center rounded-[4px] border border-rule text-ink-2 hover:text-ink xl:grid">
                <PanelRight size={16} />
              </button>
            )}
          </div>
        </div>
      </section>

      {traceOpen && !empty && (
        <div className="hidden min-h-0 w-[340px] xl:block">
          <TracePanel run={selected} trace={panelTrace} onClose={() => setTraceOpen(false)} />
        </div>
      )}
    </div>
  )
}
