import { parseFenced } from './fence'

export interface Opcion {
  label: string
  detalle: string
  recomendada: boolean
}

export interface Opciones {
  pregunta: string
  opciones: Opcion[]
}

export interface ParsedOpciones {
  before: string
  after: string
  opciones: Opciones | null
  /** an opening ```opciones fence was seen but not closed yet (only while streaming) */
  pending: boolean
}

export const MAX_OPCIONES = 6
const MAX_LABEL = 80
const MAX_DETALLE = 200
const MAX_PREGUNTA = 300

const clip = (v: unknown, max: number) => {
  const t = typeof v === 'string' ? v.trim() : ''
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t
}

export function toOpciones(value: unknown): Opciones | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  if (!Array.isArray(o.opciones)) return null
  const opciones: Opcion[] = []
  for (const raw of o.opciones) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue
    const r = raw as Record<string, unknown>
    const label = clip(r.label, MAX_LABEL)
    if (!label) continue
    opciones.push({ label, detalle: clip(r.detalle, MAX_DETALLE), recomendada: r.recomendada === true })
    if (opciones.length === MAX_OPCIONES) break
  }
  return opciones.length ? { pregunta: clip(o.pregunta, MAX_PREGUNTA), opciones } : null
}

export function parseOpciones(text: string, streaming = false): ParsedOpciones {
  const { before, after, value, pending } = parseFenced(text, 'opciones', toOpciones, streaming)
  return { before, after, opciones: value, pending }
}

export const replyText = (n: number, label: string) => `${n}. ${label}`

/** Index of the option a reply picked, matched by its `<n>.` prefix or by its label. */
export function chosenIndex(opciones: Opcion[], reply: string): number {
  const text = reply.trim()
  const m = /^(\d+)\.\s/.exec(text)
  if (m) {
    const i = Number(m[1]) - 1
    if (opciones[i] && text.slice(m[0].length).trim() === opciones[i].label) return i
  }
  return opciones.findIndex((o) => o.label === text)
}

/** One line per card, in card order: what a grouped reply sends. */
export const groupReply = (lines: string[]) => lines.join('\n')

/** The part of a grouped reply that belongs to card `k` of `total`; the whole reply when it does not split cleanly. */
export function replyForCard(reply: string, k: number, total: number): string {
  if (total <= 1) return reply
  const lines = reply.split('\n').map((l) => l.trim()).filter(Boolean)
  return lines.length === total ? lines[k] : reply
}

/** The user's reply to card `k` of `total` only when it really picks one of its options; any other message leaves the card open. */
export function answerForCard(opciones: Opcion[], reply: string | null | undefined, k: number, total: number): string | null {
  if (!reply) return null
  const line = replyForCard(reply, k, total)
  return chosenIndex(opciones, line) >= 0 ? line : null
}
