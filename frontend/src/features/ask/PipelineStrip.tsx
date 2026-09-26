import { useTranslation } from 'react-i18next'
import { formatMs } from '@/lib/format'
import { PIPELINE_STEPS, type TraceStep } from './types'

const TONE: Record<string, string> = {
  ok: 'bg-ok',
  error: 'bg-block',
  skip: 'bg-rule',
  start: 'bg-accent animate-pulse',
  pending: 'bg-surface-2',
}

/** Canonical order, with repair steps slotted in after the step they fixed. */
export function orderedSteps(trace: TraceStep[]): TraceStep[] {
  const latest = new Map<string, TraceStep>()
  const repairs: TraceStep[] = []
  for (const step of trace) {
    if (step.step === 'repair') {
      if (step.status !== 'start') repairs.push(step)
    } else latest.set(step.step, step)
  }
  const result: TraceStep[] = []
  for (const name of PIPELINE_STEPS) {
    result.push(latest.get(name) ?? { step: name, status: 'skip' as const, detail: { pending: true } })
    if (name === 'execute') result.push(...repairs)
  }
  return result
}

export function PipelineStrip({
  trace,
  live = false,
  onOpen,
}: {
  trace: TraceStep[]
  live?: boolean
  onOpen?: () => void
}) {
  const { t } = useTranslation()
  const steps = orderedSteps(trace)
  const current = live ? [...trace].reverse().find((s) => s.status === 'start') : undefined
  const total = trace.reduce((sum, s) => sum + (s.status !== 'start' ? s.duration_ms ?? 0 : 0), 0)
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={t('ask.showTrace')}
      className="group flex w-full items-center gap-3 text-left"
    >
      <span className="flex flex-1 gap-[3px]" aria-hidden>
        {steps.map((step, i) => {
          const pending = step.detail?.pending === true
          const tone = pending ? (live ? TONE.pending : TONE.skip) : TONE[step.status]
          return (
            <span
              key={`${step.step}-${i}`}
              title={`${t(`trace.steps.${step.step}`)}${step.duration_ms ? ` · ${formatMs(step.duration_ms)}` : ''}`}
              className={`h-1.5 flex-1 rounded-[1px] transition-colors duration-300 ${tone} ${
                step.step === 'repair' ? 'max-w-3' : ''
              }`}
            />
          )
        })}
      </span>
      <span className="w-40 shrink-0 truncate text-right font-mono text-[11px] text-ink-3 group-hover:text-ink-2">
        {current ? `${t(`trace.steps.${current.step}`)}…` : live ? t('ask.thinking') : formatMs(total)}
      </span>
    </button>
  )
}
