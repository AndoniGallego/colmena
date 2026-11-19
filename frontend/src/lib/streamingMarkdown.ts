export const STREAM_MARKDOWN_MS = 100

export type StreamingMarkdownThrottle = {
  update(text: string): void
  finish(): void
  renderCount: number
  latest: string
}

export function createStreamingMarkdownThrottle(
  onRender: (text: string) => void,
  intervalMs = STREAM_MARKDOWN_MS,
  now: () => number = () => Date.now(),
): StreamingMarkdownThrottle {
  let latest = ''
  let renderCount = 0
  let lastRenderAt = -Infinity
  let timer: ReturnType<typeof setTimeout> | null = null

  const invoke = () => {
    renderCount++
    onRender(latest)
    lastRenderAt = now()
  }

  const clear = () => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const scheduleTrailing = () => {
    if (timer !== null) return
    const wait = Math.max(0, intervalMs - (now() - lastRenderAt))
    timer = setTimeout(() => {
      timer = null
      invoke()
    }, wait)
  }

  const update = (text: string) => {
    latest = text
    const elapsed = now() - lastRenderAt
    if (renderCount === 0 || elapsed >= intervalMs) {
      clear()
      invoke()
      return
    }
    scheduleTrailing()
  }

  const finish = () => {
    clear()
    invoke()
  }

  return {
    update,
    finish,
    get renderCount() {
      return renderCount
    },
    get latest() {
      return latest
    },
  }
}
