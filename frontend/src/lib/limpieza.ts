import type { LimpiezaBloqueo, LimpiezaItem, LimpiezaPreviewItem, LimpiezaRazon } from '../api/types'
import { parseFenced } from './fence'

export const DIAS_MIN = 1
export const DIAS_MAX = 30
export const HOLD_MS = 1000

export const itemKey = (i: { tipo: string; target_id: string }) => `${i.tipo}:${i.target_id}`

export const clampDias = (n: number) => Math.min(DIAS_MAX, Math.max(DIAS_MIN, Math.round(Number.isFinite(n) ? n : DIAS_MIN)))

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

export function razonLabel(r: LimpiezaRazon): string {
  if (r.tipo === 'quieto') return `quieta hace ${plural(r.dias, 'día', 'días')}`
  if (r.tipo === 'sin_claude') return `sin Claude · ${plural(r.dias, 'día', 'días')} sin cambios`
  return `rama mergeada · ${r.rama}`
}

export const razonIcon = (r: LimpiezaRazon): 'pulse' | 'terminal' | 'check' => (r.tipo === 'quieto' ? 'pulse' : r.tipo === 'sin_claude' ? 'terminal' : 'check')

export const bloqueoLabel = (b: LimpiezaBloqueo): string => (b === 'corriendo' ? 'Tiene un proceso corriendo' : 'Tiene una respuesta sin leer')

export const chipLabel = (n: number) => (n === 1 ? '1 sesión quieta' : `${n} sesiones quietas`)

export const selectable = (i: LimpiezaItem) => i.bloqueado === null

export interface Grupo {
  workspace: string
  items: LimpiezaItem[]
}

/** Los elegibles agrupados por workspace en el orden que llegan; los bloqueados van aparte, al final. */
export function agrupar(items: LimpiezaItem[]): { grupos: Grupo[]; bloqueados: LimpiezaItem[] } {
  const grupos: Grupo[] = []
  for (const i of items.filter(selectable)) {
    const g = grupos.find((x) => x.workspace === i.workspace)
    if (g) g.items.push(i)
    else grupos.push({ workspace: i.workspace, items: [i] })
  }
  return { grupos, bloqueados: items.filter((i) => !selectable(i)) }
}

/** Qué marcar al abrir la hoja: la preselección de Centinela (solo ids que sean candidatos libres) o lo que propone el server. */
export function marcasIniciales(items: LimpiezaItem[], preseleccion?: string[] | null): Record<string, boolean> {
  const wanted = preseleccion ? new Set(preseleccion) : null
  const out: Record<string, boolean> = {}
  for (const i of items) {
    if (!selectable(i)) continue
    out[itemKey(i)] = wanted ? wanted.has(i.target_id) : i.marcado
  }
  return out
}

/** Motivo en ámbar para una fila que el server no deja cerrar en la revisión. */
export function motivoRevision(p: LimpiezaPreviewItem): string | null {
  if (p.bloqueantes.length || (p.preview && p.preview.bloqueantes.length)) {
    const only = [...p.bloqueantes, ...(p.preview?.bloqueantes ?? [])].every((b) => b.status === 'unknown')
    return only ? 'No sé si está trabajando' : 'Está trabajando'
  }
  if (p.error || !p.preview) {
    const e = p.error.toLowerCase()
    if (!e) return 'Cambió'
    if (e.includes('cambi')) return 'Cambió'
    if (e.includes('ya no está')) return 'Ya no está'
    return p.error
  }
  return null
}

export interface Limpiar {
  preseleccion: string[]
}

const TARGET = /^[A-Za-z0-9][A-Za-z0-9_:.-]*$/

export function toLimpiar(value: unknown): Limpiar | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const raw = (value as Record<string, unknown>).preseleccion
  if (!Array.isArray(raw)) return null
  const ids = raw.filter((x): x is string => typeof x === 'string' && TARGET.test(x.trim())).map((x) => x.trim())
  return { preseleccion: [...new Set(ids)].slice(0, 12) }
}

export interface ParsedLimpiar {
  before: string
  after: string
  limpiar: Limpiar | null
  pending: boolean
}

export function parseLimpiar(text: string, streaming = false): ParsedLimpiar {
  const { before, after, value, pending } = parseFenced(text, 'limpieza', toLimpiar, streaming)
  return { before, after, limpiar: value, pending }
}
