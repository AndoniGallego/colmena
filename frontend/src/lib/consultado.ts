export type ConsultadoEstado = 'mandando' | 'ok' | 'error' | 'incierto' | 'rechazada'

/** A question the server put to an idle session on its own, so Centinela can answer the user. */
export interface Consultado {
  id: string
  pane_id: string
  destino: string
  session_id: string
  estado: ConsultadoEstado
  motivo: string
  detalle: string
}

const ESTADOS: ConsultadoEstado[] = ['mandando', 'ok', 'error', 'incierto', 'rechazada']
const s = (v: unknown) => (typeof v === 'string' ? v.trim() : v == null ? '' : String(v))

export function toConsultado(value: unknown): Consultado | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const estado = s(o.estado) as ConsultadoEstado
  const c: Consultado = {
    id: s(o.id),
    pane_id: s(o.pane_id),
    destino: s(o.destino),
    session_id: s(o.session_id),
    estado: ESTADOS.includes(estado) ? estado : 'incierto',
    motivo: s(o.motivo),
    detalle: s(o.detalle),
  }
  return c.id ? c : null
}
