import { describe, expect, it } from 'vitest'
import { parseSseChunk } from '@/lib/sse'

describe('parseSseChunk', () => {
  it('parses complete events and keeps the partial tail', () => {
    const { events, rest } = parseSseChunk('event: step\ndata: {"step":"link"}\n\nevent: result\ndata: {"id"')
    expect(events).toEqual([{ event: 'step', data: { step: 'link' } }])
    expect(rest).toBe('event: result\ndata: {"id"')
  })

  it('handles CRLF, multi-line data and missing event names', () => {
    const { events } = parseSseChunk('data: {"a":\r\ndata: 1}\r\n\r\n')
    expect(events).toEqual([{ event: 'message', data: { a: 1 } }])
  })

  it('falls back to raw text for non-JSON data', () => {
    expect(parseSseChunk('event: ping\ndata: hello\n\n').events).toEqual([{ event: 'ping', data: 'hello' }])
  })
})
