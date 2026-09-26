import { ArrowDown, ArrowUp, GripVertical, Lock } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { AdminSettings } from './api'

/** Reorder the failover chain by drag-and-drop or the arrow buttons; rule_based is pinned last. */
export function ChainEditor({
  chain,
  providers,
  onChange,
  onResetCircuit,
}: {
  chain: string[]
  providers: AdminSettings['providers']
  onChange: (chain: string[]) => void
  onResetCircuit: (name: string) => void
}) {
  const { t } = useTranslation()
  const [dragging, setDragging] = useState<string | null>(null)
  const movable = chain.filter((name) => name !== 'rule_based')

  const move = (from: number, to: number) => {
    if (to < 0 || to >= movable.length) return
    const next = [...movable]
    const [item] = next.splice(from, 1)
    next.splice(to, 0, item)
    onChange([...next, 'rule_based'])
  }

  return (
    <ol className="divide-y divide-rule overflow-hidden rounded-[6px] border border-rule bg-surface">
      {movable.map((name, index) => {
        const info = providers.find((p) => p.name === name)
        return (
          <li
            key={name}
            draggable
            onDragStart={() => setDragging(name)}
            onDragEnd={() => setDragging(null)}
            onDragOver={(event) => event.preventDefault()}
            onDrop={() => {
              if (dragging && dragging !== name) move(movable.indexOf(dragging), index)
              setDragging(null)
            }}
            className={`flex items-center gap-3 px-3 py-2.5 ${dragging === name ? 'opacity-50' : ''} ${info?.configured ? '' : 'text-ink-3'}`}
          >
            <GripVertical size={14} className="cursor-grab text-ink-3" aria-hidden />
            <span className="w-5 font-mono text-xs text-ink-3">{index + 1}</span>
            <span className="flex-1">
              <span className="font-medium">{name}</span>{' '}
              <span className="font-mono text-[11px] text-ink-3">{info?.model ?? t('admin.notConfigured')}</span>
            </span>
            {info?.circuit === 'open' || info?.circuit === 'half_open' ? (
              <button type="button" onClick={() => onResetCircuit(name)} className="rounded-[3px] border border-warn/50 px-2 py-0.5 text-xs text-warn hover:bg-warn/10">
                {t('admin.resetCircuit')}
              </button>
            ) : null}
            <button type="button" aria-label={t('admin.moveUp', { name })} disabled={index === 0} onClick={() => move(index, index - 1)} className="grid h-7 w-7 place-items-center rounded-[4px] text-ink-2 hover:bg-surface-2 disabled:opacity-30">
              <ArrowUp size={14} />
            </button>
            <button type="button" aria-label={t('admin.moveDown', { name })} disabled={index === movable.length - 1} onClick={() => move(index, index + 1)} className="grid h-7 w-7 place-items-center rounded-[4px] text-ink-2 hover:bg-surface-2 disabled:opacity-30">
              <ArrowDown size={14} />
            </button>
          </li>
        )
      })}
      <li className="flex items-center gap-3 bg-surface-2/40 px-3 py-2.5 text-ink-2">
        <Lock size={14} className="text-ink-3" aria-hidden />
        <span className="w-5 font-mono text-xs text-ink-3">{movable.length + 1}</span>
        <span className="flex-1">{t('admin.ruleBased')}</span>
      </li>
    </ol>
  )
}
