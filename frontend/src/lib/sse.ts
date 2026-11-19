export interface SSEEvent {
  event: string
  data: string
}

/** Incremental text/event-stream parser: feed() chunks as they arrive. */
export function createSSEParser(onEvent: (e: SSEEvent) => void) {
  let buffer = ''
  let event = ''
  let data: string[] = []

  const dispatch = () => {
    if (data.length) onEvent({ event: event || 'message', data: data.join('\n') })
    event = ''
    data = []
  }

  const line = (raw: string) => {
    if (raw === '') return dispatch()
    if (raw.startsWith(':')) return
    const i = raw.indexOf(':')
    const field = i === -1 ? raw : raw.slice(0, i)
    let value = i === -1 ? '' : raw.slice(i + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }

  return {
    feed(chunk: string) {
      buffer += chunk
      let nl: number
      while ((nl = buffer.search(/\r\n|\r|\n/)) !== -1) {
        const len = buffer[nl] === '\r' && buffer[nl + 1] === '\n' ? 2 : 1
        if (buffer[nl] === '\r' && nl + 1 === buffer.length) break
        line(buffer.slice(0, nl))
        buffer = buffer.slice(nl + len)
      }
    },
    end() {
      if (buffer) line(buffer)
      buffer = ''
      dispatch()
    },
  }
}
