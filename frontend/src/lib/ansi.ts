export interface AnsiSpan {
  t: string
  fg?: string
  bg?: string
  b?: boolean
  d?: boolean
  i?: boolean
  u?: boolean
  s?: boolean
}
export type AnsiLine = AnsiSpan[]

interface Style {
  fg?: string
  bg?: string
  b?: boolean
  d?: boolean
  i?: boolean
  u?: boolean
  s?: boolean
  inv?: boolean
}
interface Cell {
  ch: string
  st: Style
}

const TAB = 8
// Formato (bidi, ancho cero) y separadores de línea/párrafo: se muestran como código para que nada se disfrace.
const CF = /[\p{Cf}\p{Zl}\p{Zp}]/u
const CC = /\p{Cc}/u
const BASE = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15']
const CUBE = [0, 95, 135, 175, 215, 255]

const hex = (n: number) => n.toString(16).padStart(2, '0')
const rgb = (r: number, g: number, b: number) => {
  const c = (v: number) => Math.max(0, Math.min(255, Math.floor(v) || 0))
  return `#${hex(c(r))}${hex(c(g))}${hex(c(b))}`
}

export function palette(n: number): string {
  if (n < 16) return `var(--ansi-${BASE[n]})`
  if (n < 232) {
    const k = n - 16
    return rgb(CUBE[Math.floor(k / 36)], CUBE[Math.floor(k / 6) % 6], CUBE[k % 6])
  }
  const g = 8 + (n - 232) * 10
  return rgb(g, g, g)
}

function applySgr(st: Style, params: number[]): Style {
  let s = { ...st }
  if (!params.length) params = [0]
  for (let k = 0; k < params.length; k++) {
    const p = params[k]
    if (p === 0) s = {}
    else if (p === 1) s.b = true
    else if (p === 2) s.d = true
    else if (p === 3) s.i = true
    else if (p === 4) s.u = true
    else if (p === 7) s.inv = true
    else if (p === 9) s.s = true
    else if (p === 22) s.b = s.d = false
    else if (p === 23) s.i = false
    else if (p === 24) s.u = false
    else if (p === 27) s.inv = false
    else if (p === 29) s.s = false
    else if (p >= 30 && p <= 37) s.fg = palette(p - 30)
    else if (p >= 90 && p <= 97) s.fg = palette(p - 90 + 8)
    else if (p >= 40 && p <= 47) s.bg = palette(p - 40)
    else if (p >= 100 && p <= 107) s.bg = palette(p - 100 + 8)
    else if (p === 39) s.fg = undefined
    else if (p === 49) s.bg = undefined
    else if (p === 38 || p === 48) {
      const key = p === 38 ? 'fg' : 'bg'
      if (params[k + 1] === 5 && k + 2 < params.length) {
        s[key] = palette(Math.max(0, Math.min(255, params[k + 2])))
        k += 2
      } else if (params[k + 1] === 2 && k + 4 < params.length) {
        s[key] = rgb(params[k + 2], params[k + 3], params[k + 4])
        k += 4
      } else break
    }
  }
  return s
}

const same = (a: Style, b: Style) =>
  a.fg === b.fg && a.bg === b.bg && !!a.b === !!b.b && !!a.d === !!b.d && !!a.i === !!b.i && !!a.u === !!b.u && !!a.s === !!b.s && !!a.inv === !!b.inv

function toSpans(cells: Cell[]): AnsiLine {
  const out: AnsiLine = []
  let cur: { st: Style; t: string } | null = null
  const flush = () => {
    if (!cur) return
    const { st, t } = cur
    const span: AnsiSpan = { t }
    const fg = st.inv ? (st.bg ?? 'var(--term-bg)') : st.fg
    const bg = st.inv ? (st.fg ?? 'var(--term-fg)') : st.bg
    if (fg) span.fg = fg
    if (bg) span.bg = bg
    if (st.b) span.b = true
    if (st.d) span.d = true
    if (st.i) span.i = true
    if (st.u) span.u = true
    if (st.s) span.s = true
    out.push(span)
  }
  for (const c of cells) {
    if (cur && same(cur.st, c.st)) cur.t += c.ch
    else {
      flush()
      cur = { st: c.st, t: c.ch }
    }
  }
  flush()
  return out
}

const codeLabel = (ch: string) => `⟨U+${(ch.codePointAt(0) ?? 0).toString(16).toUpperCase().padStart(4, '0')}⟩`

/**
 * Parser propio: solo SGR. Todo lo demás (OSC, CSI no SGR, otras secuencias ESC) se descarta; los caracteres de
 * control y de formato (bidi, ancho cero) se muestran como ⟨U+XXXX⟩. El resultado nunca es HTML.
 */
export function parseAnsi(input: string): AnsiLine[] {
  return parseCore(input.replace(/\r\n/g, '\n'), {}, false).lines
}

interface Core {
  lines: AnsiLine[]
  /** estilo SGR vigente al terminar */
  st: Style
  /** una secuencia quedó abierta al final del texto */
  incompleto: boolean
  /** la última línea no tiene celdas */
  vacia: boolean
}

function parseCore(text: string, st0: Style, soloLinea: boolean): Core {
  const lines: AnsiLine[] = []
  let cells: Cell[] = []
  let col = 0
  let st: Style = st0
  let incompleto = false
  let i = 0
  const n = text.length

  const put = (ch: string) => {
    const cell = { ch, st }
    if (col < cells.length) cells[col] = cell
    else cells.push(cell)
    col++
  }
  const endLine = () => {
    lines.push(toSpans(cells))
    cells = []
    col = 0
  }

  while (i < n) {
    const ch = text[i]
    if (ch === '\x1b') {
      const next = text[i + 1]
      if (next === '[') {
        let j = i + 2
        while (j < n && text.charCodeAt(j) >= 0x30 && text.charCodeAt(j) <= 0x3f) j++
        while (j < n && text.charCodeAt(j) >= 0x20 && text.charCodeAt(j) <= 0x2f) j++
        const final = text[j]
        if (final === undefined) incompleto = true
        if (final === 'm') {
          const raw = text.slice(i + 2, j)
          if (/^[0-9;:]*$/.test(raw)) {
            const params = raw === '' ? [] : raw.split(/[;:]/).map((x) => (x === '' ? 0 : Math.min(999, Number(x))))
            st = applySgr(st, params)
          }
        }
        i = j + 1
        continue
      }
      if (next === ']' || next === 'P' || next === '_' || next === '^' || next === 'X') {
        let j = i + 2
        while (j < n && text[j] !== '\x07' && !(text[j] === '\x1b' && text[j + 1] === '\\')) j++
        if (j >= n) incompleto = true
        i = text[j] === '\x07' ? j + 1 : j + 2
        continue
      }
      if (next !== undefined && text.charCodeAt(i + 1) >= 0x20 && text.charCodeAt(i + 1) <= 0x2f) {
        let j = i + 1
        while (j < n && text.charCodeAt(j) >= 0x20 && text.charCodeAt(j) <= 0x2f) j++
        if (j >= n) incompleto = true
        i = j + 1
        continue
      }
      if (next === undefined) incompleto = true
      i += 2
      continue
    }
    const code = text.charCodeAt(i)
    if (code >= 0x20 && code < 0x7f) {
      put(ch)
      i++
      continue
    }
    const glyph = String.fromCodePoint(text.codePointAt(i)!)
    i += glyph.length
    if (glyph === '\n') endLine()
    else if (glyph === '\r') col = 0
    else if (glyph === '\t') {
      const to = (Math.floor(col / TAB) + 1) * TAB
      while (col < to) put(' ')
    } else if (glyph === '\x08') col = Math.max(0, col - 1)
    else if (CC.test(glyph) || CF.test(glyph)) for (const c of codeLabel(glyph)) put(c)
    else put(glyph)
  }
  const vacia = cells.length === 0
  if (soloLinea || cells.length || !lines.length) endLine()
  return { lines, st, incompleto, vacia }
}

const ESTILO = ['fg', 'bg', 'b', 'd', 'i', 'u', 's', 'inv'] as const
const claveEstilo = (st: Style) => ESTILO.map((k) => (st[k] === undefined || st[k] === false ? '' : String(st[k]))).join('|')

interface Entrada {
  spans: AnsiLine
  fin: Style
  vacia: boolean
  incompleto: boolean
}
export type CacheAnsi = Map<string, Entrada>
export const nuevoCacheAnsi = (): CacheAnsi => new Map()

/**
 * Como `parseAnsi`, pero reutiliza el resultado de cada línea ya parseada con el mismo estilo SGR de entrada
 * (el color que sigue de una línea a otra se respeta). El caché solo conserva lo usado en esta pasada.
 */
export function parseAnsiLineas(input: string, cache: CacheAnsi): AnsiLine[] {
  const partes = input.replace(/\r\n/g, '\n').split('\n')
  const usadas: CacheAnsi = new Map()
  const out: AnsiLine[] = []
  let st: Style = {}
  for (let k = 0; k < partes.length; k++) {
    const clave = `${claveEstilo(st)}\u0000${partes[k]}`
    let e = usadas.get(clave) ?? cache.get(clave)
    if (!e) {
      const r = parseCore(partes[k], st, true)
      e = { spans: r.lines[0], fin: r.st, vacia: r.vacia, incompleto: r.incompleto }
    }
    if (e.incompleto) return parseAnsi(input)
    usadas.set(clave, e)
    if (k < partes.length - 1 || !e.vacia || partes.length === 1) out.push(e.spans)
    st = e.fin
  }
  cache.clear()
  for (const [c, e] of usadas) cache.set(c, e)
  return out
}

const ids = new WeakMap<AnsiLine, number>()
let nextId = 0
/** Una clave por línea: identidad del contenido parseado + número de aparición, para que las repetidas no choquen. */
export function clavesDeLineas(lines: AnsiLine[]): string[] {
  const vistas = new Map<number, number>()
  return lines.map((l) => {
    let id = ids.get(l)
    if (id === undefined) ids.set(l, (id = nextId++))
    const n = vistas.get(id) ?? 0
    vistas.set(id, n + 1)
    return `${id}.${n}`
  })
}

/**
 * Convierte las claves por contenido en claves de vnode: las líneas que siguen conservan la suya y las líneas nuevas
 * heredan las claves de las que salieron (en orden), así Vue las parchea en lugar de desmontar y montar.
 */
export function nuevoReusoClaves(): (contenido: string[]) => string[] {
  let prevContenido: string[] = []
  let prevFinal: string[] = []
  let n = 0
  return (contenido) => {
    const finalDe = new Map<string, string>()
    prevContenido.forEach((c, i) => finalDe.set(c, prevFinal[i]))
    const nuevos = new Set(contenido)
    const libres: string[] = []
    prevContenido.forEach((c, i) => {
      if (!nuevos.has(c)) libres.push(prevFinal[i])
    })
    let l = 0
    const out = contenido.map((c) => finalDe.get(c) ?? (l < libres.length ? libres[l++] : `k${n++}`))
    prevContenido = contenido
    prevFinal = out
    return out
  }
}
