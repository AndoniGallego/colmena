export interface LineaDiff {
  k: 'hunk' | 'add' | 'del' | 'ctx'
  t: string
  a: number | null
  b: number | null
}

const HUNK = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/

/** Líneas de un diff unificado de un solo archivo (sin encabezado), con su número en el viejo (a) y el nuevo (b). */
export function parseDiff(diff: string): LineaDiff[] {
  if (!diff) return []
  const out: LineaDiff[] = []
  let a = 0
  let b = 0
  for (const raw of diff.replace(/\n$/, '').split('\n')) {
    const h = HUNK.exec(raw)
    if (h) {
      a = Number(h[1])
      b = Number(h[2])
      out.push({ k: 'hunk', t: raw, a: null, b: null })
    } else if (raw.startsWith('\\')) {
      continue
    } else if (raw.startsWith('+')) {
      out.push({ k: 'add', t: raw.slice(1), a: null, b: b++ })
    } else if (raw.startsWith('-')) {
      out.push({ k: 'del', t: raw.slice(1), a: a++, b: null })
    } else if (out.length) {
      out.push({ k: 'ctx', t: raw.slice(1), a: a++, b: b++ })
    }
  }
  return out
}
