import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from './locales/en.json'
import vi from './locales/vi.json'

export const LANGS = ['vi', 'en'] as const
export type Lang = (typeof LANGS)[number]
const STORAGE_KEY = 't2s-lang'

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'vi' || stored === 'en') return stored
  } catch {
    // storage unavailable (private mode) — fall back to default
  }
  return 'vi'
}

void i18n.use(initReactI18next).init({
  resources: { vi: { translation: vi }, en: { translation: en } },
  lng: initialLang(),
  fallbackLng: 'vi',
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lng) => {
  document.documentElement.lang = lng
  try {
    localStorage.setItem(STORAGE_KEY, lng)
  } catch {
    // ignore
  }
})

export default i18n
