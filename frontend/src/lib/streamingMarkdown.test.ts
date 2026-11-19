import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createStreamingMarkdownThrottle, STREAM_MARKDOWN_MS } from './streamingMarkdown'

describe('createStreamingMarkdownThrottle', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('20 actualizaciones en 100 ms → como mucho 2 renders', () => {
    const renders: string[] = []
    const throttle = createStreamingMarkdownThrottle((t) => renders.push(t), STREAM_MARKDOWN_MS)
    for (let i = 0; i < 20; i++) {
      throttle.update(`t${i}`)
      if (i < 19) vi.advanceTimersByTime(5)
    }
    vi.advanceTimersByTime(STREAM_MARKDOWN_MS)
    expect(renders.length).toBeLessThanOrEqual(2)
  })

  it('la última actualización siempre se renderiza', () => {
    const renders: string[] = []
    const throttle = createStreamingMarkdownThrottle((t) => renders.push(t), STREAM_MARKDOWN_MS)
    for (let i = 0; i < 20; i++) {
      throttle.update(`t${i}`)
      if (i < 19) vi.advanceTimersByTime(5)
    }
    vi.advanceTimersByTime(STREAM_MARKDOWN_MS)
    expect(renders.at(-1)).toBe('t19')
  })

  it('fin del stream renderiza en el acto', () => {
    const renders: string[] = []
    const throttle = createStreamingMarkdownThrottle((t) => renders.push(t), STREAM_MARKDOWN_MS)
    throttle.update('parcial')
    throttle.finish()
    expect(renders.at(-1)).toBe('parcial')
    vi.advanceTimersByTime(STREAM_MARKDOWN_MS * 3)
    expect(renders.at(-1)).toBe('parcial')
  })
})
