import { useTranslation } from 'react-i18next'

export function BrandMark({ inverted = false }: { inverted?: boolean }) {
  const { t } = useTranslation()
  return (
    <div className="flex items-baseline gap-2">
      <span
        aria-hidden
        className={`grid h-7 w-7 place-items-center rounded-[3px] font-mono text-sm font-medium ${
          inverted ? 'bg-[#ECEAE4] text-[#14161A]' : 'bg-ink text-paper'
        }`}
      >
        D
      </span>
      <span className="font-display text-lg font-semibold tracking-tight">{t('brand.name')}</span>
      <span className={`text-sm ${inverted ? 'text-[#A9ADB6]' : 'text-ink-3'}`}>
        {t('brand.product')}
      </span>
    </div>
  )
}
