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

describe('chart pivot', () => {
  it('turns long rows into one key per series value', async () => {
    const { pivot } = await import('@/features/ask/ResultChart')
    const result = {
      columns: ['month', 'channel', 'revenue'], column_types: ['text', 'text', 'number'], row_count: 3, truncated: false,
      rows: [['2025-01', 'offline', 17], ['2025-01', 'online', 10], ['2025-02', 'offline', 15]],
    }
    expect(pivot(result, 'month', 'channel', 'revenue')).toEqual({
      data: [{ month: '2025-01', offline: 17, online: 10 }, { month: '2025-02', offline: 15 }],
      keys: ['offline', 'online'],
    })
  })
})
