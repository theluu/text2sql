import { X } from 'lucide-react'
import { create } from 'zustand'

export interface Toast {
  id: number
  title: string
  body?: string
  tone?: 'ok' | 'warn' | 'block' | 'info'
  action?: { label: string; onClick: () => void }
}

interface ToastState {
  toasts: Toast[]
  push: (toast: Omit<Toast, 'id'>) => void
  dismiss: (id: number) => void
}

let nextId = 1

export const useToasts = create<ToastState>((set, get) => ({
  toasts: [],
  push(toast) {
    const id = nextId++
    set({ toasts: [...get().toasts, { ...toast, id }] })
    setTimeout(() => get().dismiss(id), 8000)
  },
  dismiss(id) {
    set({ toasts: get().toasts.filter((t) => t.id !== id) })
  },
}))

const BAR: Record<string, string> = { ok: 'bg-ok', warn: 'bg-warn', block: 'bg-block', info: 'bg-accent' }

export function Toasts() {
  const { toasts, dismiss } = useToasts()
  return (
    <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
      {toasts.map((toast) => (
        <div key={toast.id} role="status" className="pointer-events-auto flex overflow-hidden rounded-[6px] border border-rule bg-surface shadow-[0_8px_24px_-12px_rgba(20,22,26,0.35)]">
          <span aria-hidden className={`w-1 ${BAR[toast.tone ?? 'info']}`} />
          <div className="flex-1 px-3 py-2.5">
            <p className="text-sm font-medium text-ink">{toast.title}</p>
            {toast.body && <p className="mt-0.5 line-clamp-2 text-xs text-ink-2">{toast.body}</p>}
            {toast.action && (
              <button type="button" onClick={() => { toast.action?.onClick(); dismiss(toast.id) }} className="mt-1.5 text-xs font-medium text-accent hover:underline">
                {toast.action.label}
              </button>
            )}
          </div>
          <button type="button" aria-label="×" onClick={() => dismiss(toast.id)} className="self-start p-2 text-ink-3 hover:text-ink">
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  )
}
