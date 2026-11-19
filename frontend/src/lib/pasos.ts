export type TipoPasos = 'secuencia' | 'proceso'
export type PasoTipo = 'llamada' | 'respuesta' | 'evento' | 'error'

export interface Actor {
  id: string
  nombre: string
  icono: string
}

export interface Decision {
  pregunta: string
  /** index into `pasos`, or -1 when the branch has no (valid) target */
  si: number
  no: number
}

export interface Paso {
  id: string
  /** actor indexes (secuencia); both -1 in a proceso */
  de: number
  a: number
  texto: string
  detalle: string
  datos: string
  tipo: PasoTipo
  duracion: string
  icono: string
  decision: Decision | null
}

export interface DiagramaPasos {
  titulo: string
  resumen: string
  tipo: TipoPasos
  actores: Actor[]
  pasos: Paso[]
  notas: string[]
}

export const MAX_ACTORES = 12
export const MAX_PASOS = 60
export const MAX_NOTAS = 6
const L = { titulo: 100, resumen: 300, nombre: 24, id: 32, icono: 4, texto: 120, detalle: 400, datos: 160, duracion: 24, pregunta: 120, nota: 200 }

const clip = (v: unknown, max: number) => {
  const t = typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : ''
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t
}
const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)
const TIPOS: PasoTipo[] = ['llamada', 'respuesta', 'evento', 'error']

export function toPasos(value: unknown): DiagramaPasos | null {
  const o = obj(value)
  if (!o || !Array.isArray(o.pasos)) return null

  const actores: Actor[] = []
  if (Array.isArray(o.actores)) {
    for (const raw of o.actores) {
      const r = obj(raw)
      const id = clip(r?.id, L.id)
      if (!r || !id || actores.some((a) => a.id === id)) continue
      actores.push({ id, nombre: clip(r.nombre, L.nombre) || id, icono: clip(r.icono, L.icono) })
      if (actores.length === MAX_ACTORES) break
    }
  }
  const tipo: TipoPasos = o.tipo === 'proceso' ? 'proceso' : o.tipo === 'secuencia' ? 'secuencia' : actores.length ? 'secuencia' : 'proceso'
  if (tipo === 'secuencia' && !actores.length) return null

  const pasos: Paso[] = []
  const raws: Array<Record<string, unknown>> = []
  const seen = new Set<string>()
  for (const raw of o.pasos) {
    const r = obj(raw)
    if (!r) continue
    const texto = clip(r.texto, L.texto)
    if (!texto) continue
    let de = -1
    let a = -1
    if (tipo === 'secuencia') {
      de = actores.findIndex((x) => x.id === clip(r.de, L.id))
      if (de < 0) continue
      a = r.a == null || r.a === '' ? de : actores.findIndex((x) => x.id === clip(r.a, L.id))
      if (a < 0) continue
    }
    let id = clip(r.id, L.id)
    if (!id || seen.has(id)) id = `p${pasos.length + 1}`
    while (seen.has(id)) id += '_'
    seen.add(id)
    const t = TIPOS.includes(r.tipo as PasoTipo) ? (r.tipo as PasoTipo) : 'llamada'
    pasos.push({
      id,
      de,
      a,
      texto,
      detalle: clip(r.detalle, L.detalle),
      datos: clip(r.datos, L.datos),
      tipo: tipo === 'secuencia' && de === a && t === 'llamada' ? 'evento' : t,
      duracion: clip(r.duracion, L.duracion),
      icono: clip(r.icono, L.icono),
      decision: null,
    })
    raws.push(r)
    if (pasos.length === MAX_PASOS) break
  }
  if (!pasos.length) return null

  if (tipo === 'proceso') {
    const at = (v: unknown) => pasos.findIndex((p) => p.id === clip(v, L.id))
    pasos.forEach((p, i) => {
      const d = obj(raws[i].decision)
      const pregunta = clip(d?.pregunta, L.pregunta)
      if (d && pregunta) p.decision = { pregunta, si: at(d.si), no: at(d.no) }
    })
  }

  const notas = (Array.isArray(o.notas) ? o.notas : []).map((n) => clip(n, L.nota)).filter(Boolean).slice(0, MAX_NOTAS)
  return { titulo: clip(o.titulo, L.titulo), resumen: clip(o.resumen, L.resumen), tipo, actores, pasos, notas }
}

/** Next step index when moving forward, or null at the end. A decision follows its "sí" branch. */
export function nextOf(f: DiagramaPasos, i: number): number | null {
  const d = f.pasos[i].decision
  const n = d && d.si >= 0 ? d.si : i + 1
  return n < f.pasos.length && n !== i ? n : null
}

/** Main path from the first step following "sí" branches; each step is visited once. */
export function ruta(f: DiagramaPasos): number[] {
  const out: number[] = []
  const seen = new Set<number>()
  let i: number | null = 0
  while (i !== null && !seen.has(i)) {
    seen.add(i)
    out.push(i)
    i = nextOf(f, i)
  }
  return out
}

/** A branch jumps back when it targets the same step or an earlier one. */
export const esVuelta = (desde: number, a: number) => a >= 0 && a <= desde

/** Position (1-based) of a step on the main route; steps off the route keep their array position. */
export function numeroPaso(f: DiagramaPasos, i: number): number {
  const at = ruta(f).indexOf(i)
  return at >= 0 ? at + 1 : i + 1
}

export interface Rama {
  a: number
  vuelve: boolean
  numero: number
  texto: string
  /** what the button tells the reader: where this answer leads */
  aviso: string
}

export interface Ramas {
  pregunta: string
  si: Rama | null
  no: Rama | null
}

function rama(f: DiagramaPasos, desde: number, a: number): Rama | null {
  if (a < 0) return null
  const vuelve = esVuelta(desde, a)
  const numero = numeroPaso(f, a)
  const texto = f.pasos[a].texto
  return { a, vuelve, numero, texto, aviso: `${vuelve ? 'Volvés al' : 'Seguís en el'} paso ${numero}: ${texto}` }
}

/** The two answers of a decision step, or null when the step is not a decision. */
export function ramas(f: DiagramaPasos, i: number): Ramas | null {
  const d = f.pasos[i]?.decision
  return d ? { pregunta: d.pregunta, si: rama(f, i, d.si), no: rama(f, i, d.no) } : null
}

/** Minutes in a free-form duration like "20 min", "1,5 h" or "30 s"; null when it carries no quantity. */
export function minutosDe(duracion: string): number | null {
  const m = duracion.toLowerCase().match(/(\d+(?:[.,]\d+)?)\s*(h|hs|hr|hrs|hora|horas|m|min|mins|minuto|minutos|s|seg|segs|segundo|segundos)\b/)
  if (!m) return null
  const v = parseFloat(m[1].replace(',', '.'))
  const u = m[2]
  if (u.startsWith('h')) return v * 60
  if (u.startsWith('s')) return v / 60
  return v
}

export function formatoMinutos(min: number): string {
  const t = Math.max(1, Math.round(min))
  if (t < 60) return `~${t} min`
  const h = Math.floor(t / 60)
  const r = t % 60
  return r ? `~${h} h ${r} min` : `~${h} h`
}

export interface ResumenPasos {
  pasos: number
  decisiones: number
  minutos: number | null
  /** one line: "6 pasos · 1 decisión · ~33 min" */
  linea: string
}

/** Short summary of a finished walk: steps on the main route, decisions and the summed durations when there are any. */
export function resumenPasos(f: DiagramaPasos): ResumenPasos {
  const r = ruta(f)
  const decisiones = r.filter((i) => f.pasos[i].decision).length
  const dur = r.map((i) => minutosDe(f.pasos[i].duracion)).filter((v): v is number => v !== null)
  const minutos = dur.length ? dur.reduce((a, b) => a + b, 0) : null
  const partes = [`${r.length} ${r.length === 1 ? 'paso' : 'pasos'}`]
  if (decisiones) partes.push(`${decisiones} ${decisiones === 1 ? 'decisión' : 'decisiones'}`)
  if (minutos !== null) partes.push(formatoMinutos(minutos))
  return { pasos: r.length, decisiones, minutos, linea: partes.join(' · ') }
}

/** Actor indexes in the order they first take part along the main route. */
export function actoresEnOrden(f: DiagramaPasos): number[] {
  if (f.tipo !== 'secuencia') return []
  const out: number[] = []
  for (const i of ruta(f)) for (const a of [f.pasos[i].de, f.pasos[i].a]) if (a >= 0 && !out.includes(a)) out.push(a)
  return out
}
