import { ApiError } from './types'

export type EstadoTrabajador = 'corriendo' | 'ok' | 'error' | 'vencido' | 'cancelado' | 'interrumpido'

export interface OrigenTrabajador {
  tipo: 'claude' | 'programada' | 'manual'
  nombre?: string
  session_id?: string
  pane_id?: string
  programa_id?: string
  corrida_id?: string
}

export interface TrabajadorCursor {
  id: string
  nombre: string
  estado: EstadoTrabajador
  ruta: string
  rama: string
  base: string
  inicio: number
  fin: number | null
  codigo: number | null
  archivos: string[]
  resumen: string
  pedido: string
  origen: OrigenTrabajador
  log_recortado: boolean
}

export interface CursorEstado {
  disponible: boolean
  corriendo: number
  max_simultaneos: number
}

export interface CursorApi {
  getCursorEstado: () => Promise<CursorEstado>
  getTrabajadores: () => Promise<TrabajadorCursor[]>
  getLog: (tid: string) => Promise<string>
  postCancelar: (tid: string) => Promise<void>
}

export const TID_RE = /^[a-f0-9]{32}$/
const ESTADOS: readonly EstadoTrabajador[] = ['corriendo', 'ok', 'error', 'vencido', 'cancelado', 'interrumpido']
const TIPOS = ['claude', 'programada', 'manual'] as const
const CLAVES_ORIGEN = ['nombre', 'session_id', 'pane_id', 'programa_id', 'corrida_id'] as const

const str = (v: unknown, max = 400) => (typeof v === 'string' ? v.slice(0, max) : '')
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) ? v : null)

export function normalizarTrabajador(raw: any): TrabajadorCursor | null {
  if (!raw || typeof raw !== 'object') return null
  const id = str(raw.id, 32)
  if (!TID_RE.test(id) || !ESTADOS.includes(raw.estado)) return null
  const o = raw.origen && typeof raw.origen === 'object' ? raw.origen : {}
  const origen: OrigenTrabajador = { tipo: TIPOS.includes(o.tipo) ? o.tipo : 'manual' }
  for (const k of CLAVES_ORIGEN) {
    const v = str(o[k], 200)
    if (v) origen[k] = v
  }
  return {
    id,
    nombre: str(raw.nombre, 120),
    estado: raw.estado,
    ruta: str(raw.ruta),
    rama: str(raw.rama, 120),
    base: str(raw.base, 64),
    inicio: num(raw.inicio) ?? 0,
    fin: num(raw.fin),
    codigo: num(raw.codigo),
    archivos: Array.isArray(raw.archivos) ? raw.archivos.filter((a: unknown) => typeof a === 'string').slice(0, 200).map((a: string) => a.slice(0, 400)) : [],
    resumen: str(raw.resumen, 1500),
    pedido: str(raw.pedido, 200),
    origen,
    log_recortado: raw.log_recortado === true,
  }
}

async function call(path: string, f: typeof fetch, post = false): Promise<any> {
  let res: Response
  try {
    res = await f(path, {
      method: post ? 'POST' : 'GET',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: post ? '{}' : undefined,
    })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.status === 401 ? 'La sesión venció, volvé a entrar' : 'No pude hablar con Colmena'
    try {
      const d = await res.json()
      if (typeof d?.detail === 'string') detail = d.detail
    } catch {
      /* sin json */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

function tidValido(tid: string): string {
  if (!TID_RE.test(tid)) throw new ApiError(404, 'trabajador no encontrado')
  return tid
}

export async function getCursorEstado(f: typeof fetch = fetch): Promise<CursorEstado> {
  const raw = await call('/api/cursor/estado', f)
  return {
    disponible: raw?.disponible === true,
    corriendo: num(raw?.corriendo) ?? 0,
    max_simultaneos: num(raw?.max_simultaneos) ?? 0,
  }
}

export async function getTrabajadores(f: typeof fetch = fetch): Promise<TrabajadorCursor[]> {
  const raw = await call('/api/cursor/trabajadores', f)
  const lista = Array.isArray(raw?.trabajadores) ? raw.trabajadores : []
  return lista.map(normalizarTrabajador).filter((t: TrabajadorCursor | null): t is TrabajadorCursor => !!t)
}

export async function getLog(tid: string, f: typeof fetch = fetch): Promise<string> {
  const raw = await call(`/api/cursor/trabajadores/${tidValido(tid)}/log`, f)
  return str(raw?.texto, 8000)
}

export async function postCancelar(tid: string, f: typeof fetch = fetch): Promise<void> {
  await call(`/api/cursor/trabajadores/${tidValido(tid)}/cancelar`, f, true)
}

export const httpCursorApi: CursorApi = {
  getCursorEstado: () => getCursorEstado(),
  getTrabajadores: () => getTrabajadores(),
  getLog: (tid) => getLog(tid),
  postCancelar: (tid) => postCancelar(tid),
}
