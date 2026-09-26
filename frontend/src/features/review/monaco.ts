// Bundle Monaco locally (no CDN) with only the SQL tokenizer and the base editor worker.
import { loader } from '@monaco-editor/react'
import * as monaco from 'monaco-editor/editor/editor.api'
import 'monaco-editor/basic-languages/monaco.contribution'
import EditorWorker from 'monaco-editor/editor/editor.worker?worker'

self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })

export function defineThemes() {
  monaco.editor.defineTheme('datum-light', {
    base: 'vs',
    inherit: true,
    rules: [{ token: 'keyword', foreground: '2F5BEA' }],
    colors: { 'editor.background': '#FFFFFF', 'editorLineNumber.foreground': '#9A9EA6' },
  })
  monaco.editor.defineTheme('datum-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [{ token: 'keyword', foreground: '6D8BFF' }],
    colors: { 'editor.background': '#1B1E23', 'editorLineNumber.foreground': '#5A5F69' },
  })
}
