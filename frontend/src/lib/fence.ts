export interface Fenced<T> {
  before: string
  after: string
  value: T | null
  /** an opening fence was seen but not closed yet (only while streaming) */
  pending: boolean
}

export function lenientJson(src: string): unknown {
  const body = src.trim()
  try {
    return JSON.parse(body)
  } catch {
    /* try to repair the usual LLM slips */
  }
  const repaired = body
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/,\s*([}\]])/g, '$1')
  try {
    return JSON.parse(repaired)
  } catch {
    return undefined
  }
}

const trimJoin = (a: string) => a.replace(/\s+$/, '')

/** Splits `text` around the first ```lang fence whose JSON body `convert` accepts. */
export function parseFenced<T>(text: string, lang: string, convert: (json: unknown) => T | null, streaming: boolean): Fenced<T> {
  const plain: Fenced<T> = { before: text, after: '', value: null, pending: false }
  const open = new RegExp(`(^|\\n)[ \\t]*(\`{3,}|~{3,})[ \\t]*${lang}\\b[^\\n]*\\n`, 'i').exec(text)
  if (!open) return plain

  const fence = open[2]
  const start = open.index + open[1].length
  const bodyStart = open.index + open[0].length
  const close = new RegExp(`\\n[ \\t]*${fence[0] === '`' ? '`' : '~'}{${fence.length},}[ \\t]*(?=\\n|$)`, 'g')
  close.lastIndex = bodyStart - 1
  const m = close.exec(text)

  if (!m) {
    if (streaming) return { before: trimJoin(text.slice(0, start)), after: '', value: null, pending: true }
    const value = convert(lenientJson(text.slice(bodyStart)))
    return value ? { before: trimJoin(text.slice(0, start)), after: '', value, pending: false } : plain
  }

  const value = convert(lenientJson(text.slice(bodyStart, Math.max(bodyStart, m.index))))
  if (!value) return plain
  return {
    before: trimJoin(text.slice(0, start)),
    after: text.slice(m.index + m[0].length).replace(/^\s+/, ''),
    value,
    pending: false,
  }
}
