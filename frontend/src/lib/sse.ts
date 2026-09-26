import { ApiError, getApiConfig } from './api'

export interface SseEvent {
  event: string
  data: unknown
}

/** Parse complete `event:/data:` blocks out of a buffer; returns the unconsumed tail. */
export function parseSseChunk(buffer: string): { events: SseEvent[]; rest: string } {
  const events: SseEvent[] = []
  const blocks = buffer.split(/\r?\n\r?\n/)
  const rest = blocks.pop() ?? ''
  for (const block of blocks) {
    let event = 'message'
    const data: string[] = []
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (data.length === 0) continue
    try {
      events.push({ event, data: JSON.parse(data.join('\n')) })
    } catch {
      events.push({ event, data: data.join('\n') })
    }
  }
  return { events, rest }
}

/** POST that streams server-sent events (EventSource cannot send a body or auth header). */
export function postStream(path: string, body: unknown, onEvent: (event: SseEvent) => void, signal?: AbortSignal) {
  return streamSse(path, { method: 'POST', body: JSON.stringify(body) }, onEvent, signal)
}

export async function streamSse(
  path: string,
  init: { method: 'GET' | 'POST'; body?: string },
  onEvent: (event: SseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const config = getApiConfig()
  const headers = new Headers({ Accept: 'text/event-stream' })
  if (init.body) headers.set('Content-Type', 'application/json')
  const token = config.getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`/api${path}`, { ...init, headers, signal })
  if (!response.ok || !response.body) {
    let code = `http_${response.status}`
    try {
      const payload: unknown = await response.json()
      if (payload && typeof payload === 'object' && 'detail' in payload && typeof payload.detail === 'string') code = payload.detail
    } catch {
      // non-JSON error body
    }
    if (response.status === 401 && token) config.onUnauthorized()
    throw new ApiError(response.status, code)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseChunk(buffer)
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
  }
  if (buffer.trim()) parseSseChunk(buffer + '\n\n').events.forEach(onEvent)
}
