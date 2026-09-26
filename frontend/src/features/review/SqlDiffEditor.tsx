import { DiffEditor } from '@monaco-editor/react'
import { useEffect, useState } from 'react'
import { currentTheme } from '@/lib/theme'
import { defineThemes } from './monaco'

defineThemes()

export default function SqlDiffEditor({
  original,
  value,
  onChange,
  readOnly = false,
}: {
  original: string
  value: string
  onChange: (value: string) => void
  readOnly?: boolean
}) {
  const [theme, setTheme] = useState(currentTheme())
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(currentTheme()))
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => observer.disconnect()
  }, [])
  return (
    <DiffEditor
      height="100%"
      language="sql"
      original={original}
      modified={value}
      theme={theme === 'dark' ? 'datum-dark' : 'datum-light'}
      onMount={(editor) => {
        const modified = editor.getModifiedEditor()
        modified.onDidChangeModelContent(() => onChange(modified.getValue()))
      }}
      options={{
        renderSideBySide: true,
        readOnly,
        originalEditable: false,
        minimap: { enabled: false },
        fontFamily: "'IBM Plex Mono', ui-monospace, monospace",
        fontSize: 13,
        lineHeight: 20,
        wordWrap: 'on',
        scrollBeyondLastLine: false,
        renderOverviewRuler: false,
      }}
    />
  )
}
