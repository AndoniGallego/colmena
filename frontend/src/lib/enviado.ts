
export type EnviadoEstado = 'mandando' | 'ok' | 'error' | 'incierto'

/** An order the server already delivered on its own, because the user wrote it in full. */
export interface Enviado {
  id: string
  pane_id: string
  destino: string
  session_id: string
  texto: string
  estado: EnviadoEstado
  detalle: string
}

const ESTADOS: EnviadoEstado[] = ['mandando', 'ok', 'error', 'incierto']
const s = (v: unknown) => (typeof v === 'string' ? v.trim() : v == null ? '' : String(v))

export function toEnviado(value: unknown): Enviado | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const estado = s(o.estado) as EnviadoEstado
  const e: Enviado = {
    id: s(o.id),
    pane_id: s(o.pane_id),
    destino: s(o.destino),
    session_id: s(o.session_id),
    texto: s(o.texto),
    estado: ESTADOS.includes(estado) ? estado : 'incierto',
    detalle: s(o.detalle),
  }
  return e.id && e.texto ? e : null
}

/** Key of a card inside a multi-card reply, for executions and resolutions. */
export const parteKey = (messageId: string, id: string) => `${messageId}:${id}`

/** Ids the inline retry or correction of a direct send goes out with; the original id is already used. */
export const reintentoId = (id: string) => `${id.slice(0, 58)}-re`
export const correccionId = (id: string) => `${id.slice(0, 56)}-corr`
