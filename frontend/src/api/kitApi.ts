import { ApiError } from './types'

export interface EstadoKit {
  al_dia: boolean
  problemas: string[]
}
export interface ReglaKit {
  id: string
  titulo: string
  proposito: string
}
export interface ItemKit {
  id: string
  nombre: string
  que_hace: string
}
export interface Kit {
  estado: EstadoKit
  reglas: ReglaKit[]
  skills: ItemKit[]
  hooks: ItemKit[]
}
export interface ResultadoArreglo {
  ok: boolean
  error: string
  estado: EstadoKit
}

const str = (v: unknown, max = 600) => (typeof v === 'string' ? v.slice(0, max) : '')
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {})
const lista = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.filter((x) => x && typeof x === 'object') : [])

function normalizarEstado(raw: unknown): EstadoKit {
  const o = obj(raw)
  const problemas = (Array.isArray(o.problemas) ? o.problemas : []).filter((p): p is string => typeof p === 'string' && p !== '')
  return { al_dia: o.al_dia === true, problemas }
}

function items(raw: unknown): ItemKit[] {
  return lista(raw)
    .map((x) => ({ id: str(x.id, 120), nombre: str(x.nombre, 120), que_hace: str(x.que_hace) }))
    .filter((x) => x.id)
}

export function normalizarKit(raw: unknown): Kit {
  const o = obj(raw)
  return {
    estado: normalizarEstado(o.estado),
    reglas: lista(o.reglas)
      .map((x) => ({ id: str(x.id, 120), titulo: str(x.titulo, 200), proposito: str(x.proposito) }))
      .filter((x) => x.id),
    skills: items(o.skills),
    hooks: items(o.hooks),
  }
}

async function pedir(path: string, init: RequestInit, f: typeof fetch, fallo: string): Promise<unknown> {
  let res: Response
  try {
    res = await f(path, { credentials: 'same-origin', ...init })
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
      /* not json */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

export async function getKit(f: typeof fetch = fetch): Promise<Kit> {
  return normalizarKit(await pedir('/api/kit', {}, f, 'No pude leer el estado del kit'))
}

export async function getRegla(id: string, f: typeof fetch = fetch): Promise<string> {
  const o = obj(await pedir(`/api/kit/regla/${encodeURIComponent(id)}`, {}, f, 'No pude leer la regla'))
  return typeof o.texto === 'string' ? o.texto : ''
}

export async function arreglarKit(f: typeof fetch = fetch): Promise<ResultadoArreglo> {
  const o = obj(await pedir('/api/kit/arreglar', { method: 'POST' }, f, 'No pude arreglar el kit'))
  return { ok: o.ok === true, error: str(o.error), estado: normalizarEstado(o.estado) }
}
