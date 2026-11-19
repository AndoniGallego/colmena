import { newId } from '../lib/reply'
import { ApiError } from './types'

export interface Candidata {
  pane_id: string
  session_id: string
  nombre: string
  workspace: string
  puede: boolean
  motivo: string
}

export type PendienteEstado = 'pendiente' | 'sin_confirmar' | 'cerrando'

export interface Pendiente {
  id: string
  pane_viejo: string
  session_id: string
  nombre: string
  workspace: string
  estado: PendienteEstado
  error?: string
}

export interface MudanzaListado {
  disponible: boolean
  motivo: string
  sesiones: Candidata[]
  pendientes: Pendiente[]
}

export interface ResultadoTodas {
  ok: boolean
  mudadas: Record<string, unknown>[]
  saltadas: { pane_id: string; motivo: string }[]
  fallidas: { pane_id: string; motivo: string }[]
}

const str = (v: unknown, max = 500) => (typeof v === 'string' ? v.slice(0, max) : '')
const bool = (v: unknown) => v === true
const lista = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const ESTADOS: PendienteEstado[] = ['pendiente', 'sin_confirmar', 'cerrando']
const estado = (v: unknown): PendienteEstado => (ESTADOS.includes(v as PendienteEstado) ? (v as PendienteEstado) : 'pendiente')

function normalizeCandidata(raw: unknown): Candidata {
  const r = raw as Record<string, unknown>
  return {
    pane_id: str(r?.pane_id, 80),
    session_id: str(r?.session_id, 120),
    nombre: str(r?.nombre, 200),
    workspace: str(r?.workspace, 200),
    puede: bool(r?.puede),
    motivo: str(r?.motivo, 300),
  }
}

function normalizePendiente(raw: unknown): Pendiente {
  const r = raw as Record<string, unknown>
  const p: Pendiente = {
    id: str(r?.id, 64),
    pane_viejo: str(r?.pane_viejo, 80),
    session_id: str(r?.session_id, 120),
    nombre: str(r?.nombre, 200),
    workspace: str(r?.workspace, 200),
    estado: estado(r?.estado),
  }
  const err = str(r?.error, 300)
  if (err) p.error = err
  return p
}

export function normalizeMudanzaListado(raw: unknown): MudanzaListado {
  const r = raw as Record<string, unknown>
  return {
    disponible: r?.disponible === true,
    motivo: str(r?.motivo, 300),
    sesiones: lista(r?.sesiones).map(normalizeCandidata).filter((s) => s.pane_id),
    pendientes: lista(r?.pendientes).map(normalizePendiente).filter((p) => p.id),
  }
}

async function call(path: string, body?: unknown): Promise<unknown> {
  let res: Response
  try {
    res = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.status === 401 ? 'La sesión venció, volvé a entrar' : 'No pude mudar la sesión'
    try {
      const d = await res.json()
      if (typeof d?.detail === 'string') detail = d.detail
    } catch {
      /* not json */
    }
    const ra = Number(res.headers.get('Retry-After'))
    throw new ApiError(res.status, detail, Number.isFinite(ra) && ra > 0 ? ra : null)
  }
  return res.json()
}

export async function listarMudanza(): Promise<MudanzaListado> {
  return normalizeMudanzaListado(await call('/api/mudanza'))
}

export async function mudar(paneId: string): Promise<{ ok: true; mudanza: Record<string, unknown> }> {
  const raw = await call('/api/mudanza/execute', { id: newId(), pane_id: paneId, confirmado: true })
  return raw as { ok: true; mudanza: Record<string, unknown> }
}

export async function mudarTodas(paneIds: string[]): Promise<ResultadoTodas> {
  const raw = (await call('/api/mudanza/todas', { id: newId(), pane_ids: paneIds, confirmado: true })) as Record<string, unknown>
  return {
    ok: raw?.ok !== false,
    mudadas: lista(raw?.mudadas) as Record<string, unknown>[],
    saltadas: lista(raw?.saltadas).map((s) => {
      const x = s as Record<string, unknown>
      return { pane_id: str(x?.pane_id, 80), motivo: str(x?.motivo, 300) }
    }),
    fallidas: lista(raw?.fallidas).map((s) => {
      const x = s as Record<string, unknown>
      return { pane_id: str(x?.pane_id, 80), motivo: str(x?.motivo, 300) }
    }),
  }
}

export async function retomarMudanza(mudanzaId: string): Promise<{ ok: true; mudanza: Record<string, unknown> }> {
  const raw = await call('/api/mudanza/retomar', { id: newId(), mudanza_id: mudanzaId, confirmado: true })
  return raw as { ok: true; mudanza: Record<string, unknown> }
}
