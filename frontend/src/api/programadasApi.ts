import { ApiError } from './types'
import type { Agente, Cuando, CuerpoPrograma } from '../lib/tareas'

export interface Programa {
  id: string
  nombre: string
  repo: string
  pedido: string
  agente: Agente
  modelo: string
  cuando: Cuando
  pausada: boolean
  proxima: number | null
}

export interface Programadas {
  habilitado: boolean
  programas: Programa[]
  cursor_disponible: boolean
}

export interface Corrida {
  id: string
  programa_id: string
  nombre: string
  previsto: number | null
  inicio: number | null
  estado: string
  motivo: string
  agente: Agente
  manual: boolean
  pane_id: string
}

export interface CarpetaRepo {
  ruta: string
  nombre: string
}

const str = (v: unknown, max = 600) => (typeof v === 'string' ? v.slice(0, max) : '')
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const lista = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.filter((x) => x && typeof x === 'object') : [])
const agente = (v: unknown): Agente => (v === 'cursor' ? 'cursor' : 'claude')

function cuando(raw: unknown): Cuando {
  const o = obj(raw)
  const tipo = o.tipo === 'dias' || o.tipo === 'semanal' ? o.tipo : 'diaria'
  const dias = (Array.isArray(o.dias) ? o.dias : []).filter((d): d is number => Number.isInteger(d) && d >= 0 && d <= 6)
  return { tipo, hora: str(o.hora, 5), dias, dia: num(o.dia) }
}

export function normalizarPrograma(raw: unknown): Programa | null {
  const o = obj(raw)
  const id = str(o.id, 64)
  if (!/^[a-f0-9]{32}$/.test(id)) return null
  return { id, nombre: str(o.nombre, 80), repo: str(o.repo, 1024), pedido: str(o.pedido, 4000), agente: agente(o.agente), modelo: str(o.modelo, 80), cuando: cuando(o.cuando), pausada: o.pausada !== false, proxima: num(o.proxima) }
}

export function normalizarProgramadas(raw: unknown): Programadas {
  const o = obj(raw)
  return {
    habilitado: o.habilitado === true,
    programas: lista(o.programas).map(normalizarPrograma).filter((p): p is Programa => p !== null),
    cursor_disponible: o.cursor_disponible === true,
  }
}

export function normalizarCorridas(raw: unknown): Corrida[] {
  return lista(raw).map((o) => ({
    id: str(o.id, 64),
    programa_id: str(o.programa_id, 64),
    nombre: str(o.nombre, 80),
    previsto: num(o.previsto),
    inicio: num(o.inicio),
    estado: str(o.estado, 20),
    motivo: str(o.motivo, 400),
    agente: agente(o.agente),
    manual: o.manual === true,
    pane_id: /^w\d+:p\d+$/.test(str(o.pane_id, 20)) ? str(o.pane_id, 20) : '',
  }))
}

async function pedir(path: string, init: RequestInit, f: typeof fetch, fallo: string): Promise<unknown> {
  let res: Response
  try {
    res = await f(path, { credentials: 'same-origin', ...init, headers: init.body ? { 'Content-Type': 'application/json' } : undefined })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.status === 401 ? 'La sesión venció, volvé a entrar' : fallo
    try {
      const d = (await res.json()) as { detail?: unknown; error?: unknown }
      if (typeof d?.detail === 'string') detail = d.detail
      else if (typeof d?.error === 'string') detail = d.error
    } catch {
      /* no es json */
    }
    const ra = Number(res.headers?.get?.('Retry-After'))
    throw new ApiError(res.status, detail, Number.isFinite(ra) && ra > 0 ? ra : null)
  }
  return res.json()
}

const json = (b: unknown): RequestInit => ({ body: JSON.stringify(b) })

export async function getProgramadas(f: typeof fetch = fetch): Promise<Programadas> {
  return normalizarProgramadas(await pedir('/api/programadas', {}, f, 'No pude leer las tareas programadas'))
}
export async function getHistorial(programa = '', limite = 50, f: typeof fetch = fetch): Promise<Corrida[]> {
  const q = new URLSearchParams({ limite: String(limite) })
  if (programa) q.set('programa', programa)
  return normalizarCorridas(await pedir(`/api/programadas/historial?${q}`, {}, f, 'No pude leer el historial'))
}
export async function crearPrograma(b: CuerpoPrograma, f: typeof fetch = fetch): Promise<Programa | null> {
  return normalizarPrograma(await pedir('/api/programadas', { method: 'POST', ...json(b) }, f, 'No pude guardar la tarea'))
}
export async function editarPrograma(id: string, b: CuerpoPrograma, f: typeof fetch = fetch): Promise<Programa | null> {
  return normalizarPrograma(await pedir(`/api/programadas/${id}`, { method: 'PUT', ...json(b) }, f, 'No pude guardar la tarea'))
}
export async function borrarPrograma(id: string, f: typeof fetch = fetch): Promise<void> {
  await pedir(`/api/programadas/${id}`, { method: 'DELETE' }, f, 'No pude borrar la tarea')
}
export async function pausarPrograma(id: string, pausada: boolean, f: typeof fetch = fetch): Promise<Programa | null> {
  return normalizarPrograma(await pedir(`/api/programadas/${id}/pausa`, { method: 'POST', ...json({ pausada }) }, f, 'No pude cambiar la tarea'))
}
export async function correrAhora(id: string, opId: string, f: typeof fetch = fetch): Promise<void> {
  await pedir(`/api/programadas/${id}/correr`, { method: 'POST', ...json({ id: opId }) }, f, 'No pude correr la tarea')
}
export async function habilitarProgramadas(habilitado: boolean, pin?: string, f: typeof fetch = fetch): Promise<boolean> {
  const o = obj(await pedir('/api/programadas/habilitar', { method: 'POST', ...json(pin ? { habilitado, pin } : { habilitado }) }, f, 'No pude cambiar el interruptor'))
  return o.habilitado === true
}
export async function getCarpetasRepo(f: typeof fetch = fetch): Promise<CarpetaRepo[]> {
  const d = obj(await pedir('/api/terminales/carpetas', {}, f, 'No pude leer las carpetas'))
  return lista(d.carpetas)
    .filter((c) => c.repo === true && typeof c.ruta === 'string' && typeof c.nombre === 'string')
    .map((c) => ({ ruta: str(c.ruta, 1024), nombre: str(c.nombre, 120) }))
}
