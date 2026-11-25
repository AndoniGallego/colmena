import type { Traba, TrabaTipo } from '../api/types'
import { ago } from './time'

const ROTULO: Record<TrabaTipo, string> = {
  repetida: 'Repite lo mismo',
  fallando: 'Falla una y otra vez',
  colgada: 'Herramienta colgada',
  quieta: 'Sin actividad',
}

const TIPOS = new Set<string>(Object.keys(ROTULO))
const DETALLE_MAX = 160

/** `now` en ms; `desde` viene en segundos. */
export function rotuloTraba(t: Traba, now: number): string {
  const cuando = t.desde > 0 ? ago(new Date(t.desde * 1000).toISOString(), now) : ''
  return cuando ? `${ROTULO[t.tipo]} · ${cuando}` : ROTULO[t.tipo]
}

export function normalizeTraba(raw: unknown): Traba | undefined {
  if (!raw || typeof raw !== 'object') return undefined
  const o = raw as Record<string, unknown>
  if (typeof o.tipo !== 'string' || !TIPOS.has(o.tipo)) return undefined
  const desde = Number(o.desde)
  return {
    tipo: o.tipo as TrabaTipo,
    desde: Number.isFinite(desde) ? desde : 0,
    detalle: typeof o.detalle === 'string' ? o.detalle.slice(0, DETALLE_MAX) : '',
  }
}
