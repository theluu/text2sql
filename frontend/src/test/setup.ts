import '@testing-library/jest-dom/vitest'
import '@/i18n'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'
import i18n from '@/i18n'

// jsdom lacks scrollTo; the router calls it on navigation.
window.scrollTo = () => {}

afterEach(async () => {
  cleanup()
  vi.unstubAllGlobals()
  localStorage.clear()
  await i18n.changeLanguage('vi')
})
