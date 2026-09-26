import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { formatCell } from '@/lib/format'
import type { ResultSet } from './types'

const PAGE = 12

export function DataTable({ result }: { result: ResultSet }) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(false)
  const rows = expanded ? result.rows : result.rows.slice(0, PAGE)
  const numeric = result.column_types.map((kind) => kind === 'number')
  return (
    <div>
      <div className="max-h-[420px] overflow-auto rounded-[4px] border border-rule">
        <table className="w-full border-collapse text-[13px]">
          <thead className="sticky top-0 bg-surface-2">
            <tr>
              {result.columns.map((column, i) => (
                <th key={column} scope="col" className={`whitespace-nowrap border-b border-rule px-3 py-1.5 font-mono text-[11px] font-medium text-ink-2 ${numeric[i] ? 'text-right' : 'text-left'}`}>
                  {column.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className="border-b border-rule/60 last:border-0 odd:bg-surface even:bg-paper/40">
                {row.map((cell, c) => (
                  <td key={c} className={`px-3 py-1.5 ${numeric[c] ? 'text-right font-mono tabular-nums' : ''}`}>
                    {formatCell(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.rows.length > PAGE && (
        <button type="button" onClick={() => setExpanded(!expanded)} className="mt-1.5 text-xs text-accent hover:underline">
          {expanded ? t('ask.showFewerRows') : t('ask.showAllRows', { count: result.rows.length })}
        </button>
      )}
    </div>
  )
}
