import '@testing-library/jest-dom/vitest'
import '@/i18n'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import i18n from '@/i18n'

// jsdom lacks scrollTo; the router calls it on navigation.
window.scrollTo = () => {}
Element.prototype.scrollIntoView = () => {}
// Recharts' ResponsiveContainer measures with ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

afterEach(async () => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  await i18n.changeLanguage('vi')
})
