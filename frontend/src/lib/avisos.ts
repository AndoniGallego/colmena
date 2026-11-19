import type { Aviso, AvisoKindBase, FiltroAvisos } from '../api/types'
import { fechaLarga, hoyLocal, shiftFecha, ymd } from './fechas'

export type IconoAviso = 'ask' | 'warn' | 'check' | 'terminal' | 'clock' | 'bell' | 'link' | 'merge' | 'moon' | 'calendar' | 'board' | 'library' | 'chat' | 'grid' | 'sun' | 'sparkle' | 'pulse' | 'doc' | 'diagrama' | 'image' | 'film'

export const AVISO_ICON: Record<AvisoKindBase, IconoAviso> = {
  asks: 'ask',
  blocked: 'warn',
  done: 'check',
  terminal: 'terminal',
  encadenar: 'link',
  vigia: 'bell',
  progreso: 'bell',
  mr: 'merge',
  entorno: 'warn',
  cierre: 'moon',
  test: 'bell',
  pestana: 'terminal',
}

export const AVISO_TIPO: Record<AvisoKindBase, string> = {
  asks: 'Pregunta',
  blocked: 'Aprobación',
  done: 'Terminó',
  terminal: 'Terminal',
  encadenar: 'Encadenado',
  vigia: 'Vi esto',
  progreso: 'Avance',
  mr: 'MR',
  entorno: 'Entornos',
  cierre: 'Cierre del día',
  test: 'Prueba',
  pestana: 'Pestaña',
}

/** Lo que una pieza aporta para mostrar sus avisos. */
export interface AvisoDePieza {
  kind: string
  icono: IconoAviso
  etiqueta: string
}

const esBase = (kind: string): kind is AvisoKindBase => Object.hasOwn(AVISO_ICON, kind)

export function iconoAviso(kind: string, piezas: AvisoDePieza[] = []): IconoAviso {
  return esBase(kind) ? AVISO_ICON[kind] : (piezas.find((p) => p.kind === kind)?.icono ?? 'bell')
}

export function etiquetaAviso(kind: string, piezas: AvisoDePieza[] = []): string {
  return esBase(kind) ? AVISO_TIPO[kind] : (piezas.find((p) => p.kind === kind)?.etiqueta ?? '')
}

export const diaDeAviso = (ts: number) => ymd(new Date(ts * 1000))

export function etiquetaDia(fecha: string, hoy = hoyLocal()): string {
  if (fecha === hoy) return 'Hoy'
  if (fecha === shiftFecha(hoy, -1)) return 'Ayer'
  return fechaLarga(fecha)
}

export function horaDeAviso(ts: number): string {
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export interface GrupoAvisos {
  fecha: string
  label: string
  items: Aviso[]
}

/** Agrupa por día local manteniendo el orden recibido (más nuevo primero). */
export function agruparAvisos(items: Aviso[], hoy = hoyLocal()): GrupoAvisos[] {
  const out: GrupoAvisos[] = []
  for (const a of items) {
    const fecha = diaDeAviso(a.ts)
    const last = out[out.length - 1]
    if (last && last.fecha === fecha) last.items.push(a)
    else out.push({ fecha, label: etiquetaDia(fecha, hoy), items: [a] })
  }
  return out
}

export type DestinoAviso =
  | { tipo: 'sesion'; id: string }
  | { tipo: 'terminal'; id: string }
  | { tipo: 'pieza'; kind: string }
  | { tipo: 'mr'; ref: string }
  | { tipo: 'tablero' }
  | { tipo: 'ninguno' }

/** `kindsPieza`: kinds que registran las piezas montadas; cada pieza decide adónde lleva su aviso. */
export function destinoDeAviso(a: Aviso, kindsPieza: string[] = []): DestinoAviso {
  if (kindsPieza.includes(a.kind)) return { tipo: 'pieza', kind: a.kind }
  if (a.kind === 'cierre' || a.kind === 'encadenar' || a.kind === 'vigia') return { tipo: 'tablero' }
  if (a.kind === 'mr') return /^\d{1,12}:\d{1,9}$/.test(a.mr) ? { tipo: 'mr', ref: a.mr } : { tipo: 'ninguno' }
  if (a.kind === 'terminal') return a.pane_id ? { tipo: 'terminal', id: a.pane_id } : { tipo: 'ninguno' }
  if (a.session_id && (a.kind === 'asks' || a.kind === 'blocked' || a.kind === 'done')) return { tipo: 'sesion', id: a.session_id }
  return { tipo: 'ninguno' }
}

export function coincideAviso(a: Aviso, f: FiltroAvisos): boolean {
  if ('session_id' in f) return !!a.session_id && a.session_id === f.session_id
  if ('pane_id' in f) return !!a.pane_id && a.pane_id === f.pane_id
  if ('mr' in f) return !!a.mr && a.mr === f.mr
  if ('mensaje' in f) return !!a.mensaje && a.mensaje === f.mensaje
  return a.kind === f.kind
}

/** Tags de avisos ya leídos que no tienen otro aviso sin leer con el mismo tag. */
export function tagsCerrables(items: Aviso[], leidosHasta: number): string[] {
  const leidos = new Set<string>()
  const sinLeer = new Set<string>()
  for (const a of items) {
    if (!a.tag) continue
    if (a.leido || a.id <= leidosHasta) leidos.add(a.tag)
    else sinLeer.add(a.tag)
  }
  return [...leidos].filter((t) => !sinLeer.has(t)).sort()
}

export function mezclarAvisos(actuales: Aviso[], nuevos: Aviso[]): Aviso[] {
  const byId = new Map<number, Aviso>()
  for (const a of actuales) byId.set(a.id, a)
  for (const a of nuevos) byId.set(a.id, a)
  return [...byId.values()].sort((a, b) => b.id - a.id)
}
