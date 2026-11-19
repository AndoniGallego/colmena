export type AvisoTipo = 'fin' | 'pregunta' | 'error' | 'info'

export interface AvisoRef {
  pane_id?: string
  session_id?: string
  tipo: AvisoTipo
  titulo: string
  texto: string
}

const TIPOS = new Set<AvisoTipo>(['fin', 'pregunta', 'error', 'info'])

const clip = (v: unknown, max: number) => {
  const t = typeof v === 'string' ? v.trim() : ''
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t
}

export function toAvisoRef(value: unknown): AvisoRef | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const tipo = clip(o.tipo, 20) as AvisoTipo
  if (!TIPOS.has(tipo)) return null
  const titulo = clip(o.titulo, 80)
  const texto = clip(o.texto, 300)
  if (!titulo || !texto) return null
  const pane = clip(o.pane_id, 64)
  const sid = clip(o.session_id, 64)
  if (!pane && !sid) return null
  const out: AvisoRef = { tipo, titulo, texto }
  if (pane) out.pane_id = pane
  if (sid) out.session_id = sid
  return out
}

export const avisoStatus = (tipo: AvisoTipo) =>
  ({ fin: 'done', pregunta: 'blocked', error: 'blocked', info: 'idle' } as const)[tipo]
