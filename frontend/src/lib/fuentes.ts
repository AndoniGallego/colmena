import { parseFenced } from './fence'
import { mesCorto } from './fechas'
import type { MemoriaCitaRef } from '../api/types'

export type Fuente =
  | { tipo: 'sesion'; session_id: string; turno: number; titulo: string; fecha: string }
  | { tipo: 'engram'; id: number; titulo: string; fecha: string; proyecto: string }

export const MAX_FUENTES = 6
const SESSION_RE = /^[A-Za-z0-9_-]{1,80}$/
const FECHA_RE = /^\d{4}-\d{2}-\d{2}/
const MCP = 'mcp__memoria__'

const entero = (v: unknown, min: number) => (typeof v === 'number' && Number.isInteger(v) && v >= min ? v : null)
const texto = (v: unknown, max: number) => (typeof v === 'string' ? v.trim().slice(0, max) : '')
const fecha = (v: unknown) => (typeof v === 'string' && FECHA_RE.test(v) ? v.slice(0, 10) : '')

function toFuente(raw: any): Fuente | null {
  if (!raw || typeof raw !== 'object') return null
  if (raw.tipo === 'sesion') {
    const turno = entero(raw.turno, 0)
    if (typeof raw.session_id !== 'string' || !SESSION_RE.test(raw.session_id) || turno === null) return null
    return { tipo: 'sesion', session_id: raw.session_id, turno, titulo: texto(raw.titulo, 80) || 'Sesión', fecha: fecha(raw.fecha) }
  }
  if (raw.tipo === 'engram') {
    const id = entero(raw.id, 1)
    if (id === null) return null
    return { tipo: 'engram', id, titulo: texto(raw.titulo, 80) || `Memoria #${id}`, fecha: fecha(raw.fecha), proyecto: texto(raw.proyecto, 40) }
  }
  return null
}

/** Always yields a list (maybe empty) so a malformed block is hidden instead of shown as code. */
export function toFuentes(json: unknown): { items: Fuente[] } {
  const list = Array.isArray(json) ? json : []
  const seen = new Set<string>()
  const items: Fuente[] = []
  for (const raw of list) {
    const f = toFuente(raw)
    if (!f) continue
    const key = fuenteKey(f)
    if (seen.has(key)) continue
    seen.add(key)
    items.push(f)
    if (items.length >= MAX_FUENTES) break
  }
  return { items }
}

export const fuenteKey = (f: Fuente) => (f.tipo === 'sesion' ? `s:${f.session_id}:${f.turno}` : `e:${f.id}`)

export const citaRef = (f: Fuente): MemoriaCitaRef =>
  f.tipo === 'sesion' ? { tipo: 'sesion', session_id: f.session_id, turno: f.turno } : { tipo: 'engram', id: f.id }

export interface SplitFuentes {
  text: string
  fuentes: Fuente[]
  pending: boolean
}

/** Pulls the ```fuentes block out of a message; while streaming an unclosed block is hidden. */
export function splitFuentes(text: string, streaming: boolean): SplitFuentes {
  const r = parseFenced(text, 'fuentes', toFuentes, streaming)
  if (r.pending) return { text: r.before, fuentes: [], pending: true }
  if (!r.value) return { text, fuentes: [], pending: false }
  return { text: r.after ? `${r.before}\n\n${r.after}` : r.before, fuentes: r.value.items, pending: false }
}

export const fechaCorta = (f: string) => (FECHA_RE.test(f) ? `${Number(f.slice(8, 10))} ${mesCorto(f.slice(0, 10))}` : '')

export const esMemoria = (name: string) => name.startsWith(MCP)

export type PasoIcono = 'search' | 'brain' | 'doc'

export function pasoMemoria(name: string, summary: string): { icon: PasoIcono; label: string } {
  const tool = name.slice(MCP.length)
  const s = summary.trim()
  switch (tool) {
    case 'buscar_sesiones':
      return { icon: 'search', label: s ? `Buscando en tus sesiones: «${s}»` : 'Buscando en tus sesiones' }
    case 'buscar_memoria':
      return { icon: 'brain', label: s ? `Buscando en Engram: ${s}` : 'Buscando en Engram' }
    case 'leer_sesion': {
      const m = /^(.*) · (\d{4}-\d{2}-\d{2})$/.exec(s)
      if (m) return { icon: 'doc', label: `Leyendo «${m[1]}» (${fechaCorta(m[2])})` }
      return { icon: 'doc', label: 'Leyendo una sesión' }
    }
    case 'leer_memoria':
      return { icon: 'brain', label: s ? `Leyendo la memoria ${s}` : 'Leyendo una memoria' }
    case 'linea_de_tiempo':
      return { icon: 'brain', label: s ? `Mirando qué pasó alrededor de ${s}` : 'Mirando la línea de tiempo' }
    default:
      return { icon: 'brain', label: 'Mirando lo último en Engram' }
  }
}

export const lugares = (n: number) => `Buscó en ${n} ${n === 1 ? 'lugar' : 'lugares'}`

const mb = (n: number) => `${n < 10 ? n.toFixed(1).replace('.', ',') : Math.round(n)} MB`

/** "93 sesiones · 24 MB · actualizado hace 2 min" */
export function resumenIndice(e: { indexados: number; tamano_mb: number; ultima_actualizacion: string | null; actualizando: boolean }, hace: string): string {
  if (e.actualizando && !e.indexados) return 'Armando el índice…'
  if (!e.indexados) return 'Todavía no hay nada indexado'
  const partes = [`${e.indexados} ${e.indexados === 1 ? 'sesión' : 'sesiones'}`, mb(e.tamano_mb)]
  if (e.actualizando) partes.push('actualizando…')
  else if (hace) partes.push(`actualizado ${hace}`)
  return partes.join(' · ')
}
