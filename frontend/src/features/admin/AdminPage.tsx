import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ApiError } from '@/lib/api'
import { adminKeys, type Features, type RiskSettings, resetCircuit, saveSettings, useAdminSettings, useSemantic } from './api'
import { ChainEditor } from './ChainEditor'

const RISK_FIELDS: { key: keyof RiskSettings; step: number; min: number; max?: number }[] = [
  { key: 'review_confidence', step: 0.05, min: 0, max: 1 },
  { key: 'fallback_confidence', step: 0.05, min: 0, max: 1 },
  { key: 'gray_cost', step: 50_000, min: 1 },
  { key: 'max_cost', step: 1_000_000, min: 1 },
  { key: 'w_self', step: 0.05, min: 0, max: 1 },
  { key: 'w_judge', step: 0.05, min: 0, max: 1 },
  { key: 'w_agreement', step: 0.05, min: 0, max: 1 },
]

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-t border-rule py-8 lg:grid-cols-[280px_1fr]">
      <div>
        <h2 className="font-display text-lg font-semibold">{title}</h2>
        {hint && <p className="mt-1 text-sm text-ink-2">{hint}</p>}
      </div>
      <div>{children}</div>
    </section>
  )
}

function SemanticViewer() {
  const { t, i18n } = useTranslation()
  const { data } = useSemantic()
  if (!data) return null
  const en = i18n.resolvedLanguage === 'en'
  return (
    <Section title={t('admin.semantic')} hint={t('admin.semanticHint', { version: data.version, embedder: data.embedder })}>
      <div className="space-y-2">
        {data.tables.map((table) => (
          <details key={table.name} className="rounded-[4px] border border-rule bg-surface">
            <summary className="flex cursor-pointer items-baseline gap-2 px-3 py-2 text-sm">
              <span className="font-mono font-medium">{table.name}</span>
              <span className="text-ink-2">{en ? table.en : table.vi}</span>
              {table.viewer_via && <span className="ml-auto text-[11px] text-warn">{t('admin.viewerVia', { view: table.viewer_via })}</span>}
              {table.view_of && <span className="ml-auto text-[11px] text-ink-3">{t('admin.viewOf', { base: table.view_of })}</span>}
            </summary>
            <table className="w-full border-t border-rule text-xs">
              <tbody>
                {table.columns.map((c) => (
                  <tr key={c.name} className="border-b border-rule/50 last:border-0">
                    <td className="px-3 py-1 font-mono">{c.name}</td>
                    <td className="px-3 py-1 font-mono text-ink-3">{c.type}</td>
                    <td className="px-3 py-1 text-ink-2">{en ? c.en : c.vi}</td>
                    <td className="px-3 py-1">{c.pii && <span className="rounded-[3px] border border-block/40 px-1 text-[10px] text-block">PII</span>}</td>
                    <td className="px-3 py-1 font-mono text-ink-3">{c.fk ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        ))}
      </div>
      <h3 className="mt-6 text-sm font-medium text-ink-2">{t('admin.metrics')}</h3>
      <ul className="mt-2 space-y-2 text-sm">
        {data.metrics.map((m) => (
          <li key={m.name} className="rounded-[4px] border border-rule bg-surface px-3 py-2">
            <span className="font-mono font-medium">{m.name}</span> <span className="text-ink-2">{en ? m.en : m.vi}</span>
            <code className="mt-1 block font-mono text-[11.5px] text-ink-2">{m.sql}{m.filter ? `  WHERE ${m.filter}` : ''}</code>
          </li>
        ))}
      </ul>
      <h3 className="mt-6 text-sm font-medium text-ink-2">{t('admin.glossary')}</h3>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {data.glossary.map((g) => (
          <span key={`${g.term}-${g.maps_to}`} title={g.maps_to} className="rounded-[3px] border border-rule bg-surface px-1.5 py-0.5 text-xs">
            {en ? g.en : g.term} <span className="font-mono text-[10px] text-ink-3">→ {g.maps_to}</span>
          </span>
        ))}
      </div>
    </Section>
  )
}

export function AdminPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const { data, isError, refetch } = useAdminSettings()
  const [chain, setChain] = useState<string[]>([])
  const [chaos, setChaos] = useState<string[]>([])
  const [risk, setRisk] = useState<RiskSettings | null>(null)
  const [features, setFeatures] = useState<Features | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'block'; text: string } | null>(null)

  useEffect(() => {
    if (!data) return
    setChain(data.llm_chain)
    setChaos(data.chaos.disabled_providers)
    setRisk(data.risk)
    setFeatures(data.features)
  }, [data])

  const save = useMutation({
    mutationFn: () => saveSettings({ llm_chain: chain, chaos: { disabled_providers: chaos }, risk: risk ?? undefined, features: features ?? undefined }),
    onSuccess: (next) => {
      client.setQueryData(adminKeys.settings, next)
      setMessage({ tone: 'ok', text: t('admin.saved') })
    },
    onError: (error) => setMessage({ tone: 'block', text: error instanceof ApiError ? error.message : String(error) }),
  })
  const reset = useMutation({
    mutationFn: resetCircuit,
    onSuccess: () => void client.invalidateQueries({ queryKey: adminKeys.settings }),
  })

  if (isError)
    return (
      <p role="alert" className="p-8 text-sm text-block">
        {t('review.errors.load')}{' '}
        <button type="button" onClick={() => void refetch()} className="text-accent hover:underline">{t('common.retry')}</button>
      </p>
    )
  if (!data || !risk || !features) return <div className="p-8"><div className="h-6 w-1/3 animate-pulse rounded bg-surface-2" /></div>

  return (
    <section className="px-8 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl font-semibold tracking-tight">{t('admin.title')}</h1>
          <p className="mt-1 text-sm text-ink-2">{t('admin.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          {message && <p role="status" className={`text-sm ${message.tone === 'ok' ? 'text-ok' : 'text-block'}`}>{message.text}</p>}
          <button type="button" onClick={() => { setMessage(null); save.mutate() }} disabled={save.isPending} className="rounded-[4px] bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50">
            {save.isPending ? t('admin.saving') : t('admin.save')}
          </button>
        </div>
      </div>

      <div className="mt-6">
        <Section title={t('admin.chain')} hint={t('admin.chainHint')}>
          <ChainEditor chain={chain} providers={data.providers} onChange={setChain} onResetCircuit={(name) => reset.mutate(name)} />
        </Section>

        <Section title={t('admin.chaos')} hint={t('admin.chaosHint')}>
          <div className="flex flex-wrap gap-4">
            {data.providers.map((p) => (
              <label key={p.name} className={`flex items-center gap-2 text-sm ${p.configured ? '' : 'text-ink-3'}`}>
                <input type="checkbox" checked={chaos.includes(p.name)} className="accent-[var(--warn)]"
                  onChange={(e) => setChaos(e.target.checked ? [...chaos, p.name] : chaos.filter((x) => x !== p.name))} />
                {p.name}
              </label>
            ))}
          </div>
        </Section>

        <Section title={t('admin.risk')}>
          <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
            {RISK_FIELDS.map((field) => (
              <label key={field.key} className="text-sm text-ink-2">
                {t(`admin.riskFields.${field.key}`)}
                <input type="number" step={field.step} min={field.min} max={field.max} value={risk[field.key]}
                  onChange={(e) => setRisk({ ...risk, [field.key]: Number(e.target.value) })}
                  className="mt-1 block w-full rounded-[4px] border border-rule bg-surface px-2 py-1.5 font-mono text-ink focus:border-accent focus:outline-none" />
                <span className="text-[11px] text-ink-3">{t('admin.default', { value: data.risk_defaults[field.key] })}</span>
              </label>
            ))}
          </div>
          <button type="button" onClick={() => setRisk(data.risk_defaults)} className="mt-3 text-xs text-accent hover:underline">{t('admin.reset')}</button>
        </Section>

        <Section title={t('admin.features')}>
          <div className="space-y-2">
            {(Object.keys(features) as (keyof Features)[]).map((key) => (
              <label key={key} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={features[key]} onChange={(e) => setFeatures({ ...features, [key]: e.target.checked })} className="accent-[var(--accent)]" />
                {t(`admin.featureFields.${key}`)}
              </label>
            ))}
          </div>
        </Section>

        <SemanticViewer />
      </div>
    </section>
  )
}
