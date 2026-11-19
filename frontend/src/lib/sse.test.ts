import { describe, expect, it } from 'vitest'
import { createSSEParser, type SSEEvent } from './sse'

function run(chunks: string[]) {
  const out: SSEEvent[] = []
  const p = createSSEParser((e) => out.push(e))
  chunks.forEach((c) => p.feed(c))
  p.end()
  return out
}

describe('createSSEParser', () => {
  it('parses events split across arbitrary chunks', () => {
    const raw = 'event: delta\ndata: {"text":"ho"}\n\nevent: delta\ndata: {"text":"la"}\n\nevent: done\ndata: {}\n\n'
    const chunks = raw.match(/.{1,7}/gs) ?? []
    expect(run(chunks)).toEqual([
      { event: 'delta', data: '{"text":"ho"}' },
      { event: 'delta', data: '{"text":"la"}' },
      { event: 'done', data: '{}' },
    ])
  })

  it('handles CRLF split between chunks, comments and multi-line data', () => {
    expect(run([': ping\r', '\nevent: tool\r\ndata: a\r\ndata: b\r', '\n\r\n'])).toEqual([{ event: 'tool', data: 'a\nb' }])
  })

  it('flushes a trailing event without blank line on end', () => {
    expect(run(['data: x'])).toEqual([{ event: 'message', data: 'x' }])
  })
})
