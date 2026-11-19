import { parseFenced } from './fence'

export const TIPOS_ENGRAM = ['decision', 'architecture', 'bugfix', 'pattern', 'config', 'discovery', 'learning', 'manual'] as const
export type TipoEngram = (typeof TIPOS_ENGRAM)[number]

export const MAX_TITULO = 120
export const MAX_CONTENIDO = 4000
export const MAX_TOPIC = 120

export interface Engram {
  titulo: string
  tipo: TipoEngram
  contenido: string
  topic_key: string | null
}

const CAMPOS = ['titulo', 'tipo', 'contenido', 'topic_key']
const TOPIC = /^[A-Za-z0-9][A-Za-z0-9/_.:-]*$/
// eslint-disable-next-line no-control-regex
const CONTROL_TITULO = /[\x00-\x1f\x7f-\x9f\u2028\u2029\u200e\u200f\u202a-\u202e\u2066-\u2069]/
// eslint-disable-next-line no-control-regex
const CONTROL_CONTENIDO = /[\x00-\x08\x0b-\x1f\x7f-\x9f\u2028\u2029\u200e\u200f\u202a-\u202e\u2066-\u2069]/

/** Same rules as the server: any other field, type or size makes the block invalid (it is drawn as plain text). */
export function toEngram(value: unknown): Engram | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  if (Object.keys(o).some((k) => !CAMPOS.includes(k))) return null
  if (typeof o.titulo !== 'string' || typeof o.tipo !== 'string' || typeof o.contenido !== 'string') return null
  if (o.topic_key != null && typeof o.topic_key !== 'string') return null
  const titulo = o.titulo.trim()
  const contenido = o.contenido.replace(/\r\n/g, '\n').trim()
  const topic = typeof o.topic_key === 'string' ? o.topic_key.trim() : ''
  if (!titulo || titulo.length > MAX_TITULO || CONTROL_TITULO.test(titulo)) return null
  if (!(TIPOS_ENGRAM as readonly string[]).includes(o.tipo)) return null
  if (!contenido || contenido.length > MAX_CONTENIDO || CONTROL_CONTENIDO.test(contenido)) return null
  if (topic && (topic.length > MAX_TOPIC || !TOPIC.test(topic))) return null
  return { titulo, tipo: o.tipo as TipoEngram, contenido, topic_key: topic || null }
}

export const parseEngram = (text: string, streaming = false) => parseFenced(text, 'engram', toEngram, streaming)

export interface EngramRequest {
  message_id: string
  titulo: string
  tipo: string
  contenido: string
  topic_key?: string
}

export const engramBody = (messageId: string, e: Engram): EngramRequest => ({
  message_id: messageId,
  titulo: e.titulo,
  tipo: e.tipo,
  contenido: e.contenido,
  ...(e.topic_key ? { topic_key: e.topic_key } : {}),
})
