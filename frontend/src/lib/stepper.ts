import { groupReply, replyText, type Opciones } from './opciones'
import { parseSegments } from './segments'
import { coincide } from './teclas'

export type Respuesta = { kind: 'opcion'; i: number } | { kind: 'texto'; text: string }

export interface StepperState {
  /** 0..n-1 is a question, n is the summary */
  step: number
  answers: (Respuesta | null)[]
}

export interface Progreso extends StepperState {
  sig: string
  dismissed: boolean
  /** put away on purpose with the Minimizar bar (older saves do not have it) */
  minimizado?: boolean
  at: number
}

/** A message the stepper can look at: its id, whether it comes from the assistant, and its text. */
export interface MsgLite {
  id: string
  assistant: boolean
  text: string
}

export interface Pendientes {
  sig: string
  questions: Opciones[]
}

export const questionsOf = (text: string): Opciones[] =>
  parseSegments(text).flatMap((s) => (s.type === 'opciones' ? [s.data] : []))

function hash(s: string): string {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0
  return (h >>> 0).toString(36)
}

export const signature = (id: string, qs: Opciones[]) =>
  `${id}:${hash(qs.map((q) => `${q.pregunta}\u0001${q.opciones.map((o) => o.label).join('\u0002')}`).join('\u0003'))}`

/**
 * Questions still waiting for the user: only when the last message of the chat is the assistant's,
 * it carries option cards, and nothing was sent after it (`replied` covers replies not in the list yet).
 */
export function pendientes(msgs: MsgLite[], replied = false): Pendientes | null {
  if (replied || !msgs.length) return null
  const last = msgs[msgs.length - 1]
  if (!last.assistant) return null
  const questions = questionsOf(last.text)
  return questions.length ? { sig: signature(last.id, questions), questions } : null
}

const oneLine = (s: string) => s.replace(/\s+/g, ' ').trim()

export function answerLine(q: Opciones, a: Respuesta | null): string {
  if (!a) return ''
  if (a.kind === 'texto') return oneLine(a.text)
  const o = q.opciones[a.i]
  return o ? replyText(a.i + 1, o.label) : ''
}

export const isAnswered = (q: Opciones, a: Respuesta | null | undefined) => !!a && answerLine(q, a) !== ''

/** The single message the stepper sends: one line per question, in order. */
export function buildReply(qs: Opciones[], answers: (Respuesta | null)[]): string | null {
  const lines = qs.map((q, k) => answerLine(q, answers[k] ?? null))
  return lines.every(Boolean) ? groupReply(lines) : null
}

export const initial = (n: number): StepperState => ({ step: 0, answers: Array.from({ length: n }, () => null) })

const clampStep = (n: number, step: number) => Math.max(0, Math.min(n <= 1 ? 0 : n, step))

/** Summary step exists only with two or more questions. */
export const isSummary = (n: number, s: StepperState) => n > 1 && s.step === n

export const allAnswered = (qs: Opciones[], s: StepperState) => qs.every((q, k) => isAnswered(q, s.answers[k]))

/** First unanswered question after `from`, or the summary when all are answered. */
function nextOpen(qs: Opciones[], answers: (Respuesta | null)[], from: number): number {
  for (let k = from + 1; k < qs.length; k++) if (!isAnswered(qs[k], answers[k])) return k
  for (let k = 0; k <= from && k < qs.length; k++) if (!isAnswered(qs[k], answers[k])) return k
  return qs.length
}

export function answer(qs: Opciones[], s: StepperState, a: Respuesta): StepperState {
  const n = qs.length
  if (s.step >= n) return s
  const answers = [...s.answers]
  answers[s.step] = a
  return { step: s.step, answers }
}

/** After answering: the next open question, or the summary once everything is answered. */
export function advance(qs: Opciones[], s: StepperState): StepperState {
  if (qs.length <= 1 || !canNext(qs, s)) return s
  return { ...s, step: nextOpen(qs, s.answers, s.step) }
}

export function canNext(qs: Opciones[], s: StepperState): boolean {
  if (s.step >= qs.length) return false
  return isAnswered(qs[s.step], s.answers[s.step])
}

export function next(qs: Opciones[], s: StepperState): StepperState {
  if (!canNext(qs, s) || qs.length <= 1) return s
  return { ...s, step: s.step + 1 }
}

export const back = (s: StepperState): StepperState => (s.step > 0 ? { ...s, step: s.step - 1 } : s)

/** Jump only to a question already reached: answered ones, the first open one, or the summary when complete. */
export function goTo(qs: Opciones[], s: StepperState, step: number): StepperState {
  const n = qs.length
  const target = clampStep(n, step)
  if (target === s.step) return s
  if (target === n) return allAnswered(qs, s) ? { ...s, step: target } : s
  const firstOpen = qs.findIndex((q, k) => !isAnswered(q, s.answers[k]))
  if (isAnswered(qs[target], s.answers[target]) || target === firstOpen || target < s.step) return { ...s, step: target }
  return s
}

/** Brings a saved progress back only when it belongs to the same questions. */
export function restore(qs: Opciones[], sig: string, saved: Progreso | null | undefined): { state: StepperState; dismissed: boolean; minimizado: boolean } {
  if (!saved || saved.sig !== sig || !Array.isArray(saved.answers) || saved.answers.length !== qs.length) {
    return { state: initial(qs.length), dismissed: false, minimizado: false }
  }
  const answers = saved.answers.map((a, k) => {
    if (!a || typeof a !== 'object') return null
    if (a.kind === 'opcion' && Number.isInteger(a.i) && qs[k].opciones[a.i]) return { kind: 'opcion', i: a.i } as Respuesta
    if (a.kind === 'texto' && typeof a.text === 'string') return { kind: 'texto', text: a.text } as Respuesta
    return null
  })
  const state = { step: clampStep(qs.length, Number(saved.step) || 0), answers }
  if (isSummary(qs.length, state) && !allAnswered(qs, state)) state.step = nextOpen(qs, answers, -1)
  const minimizado = !!saved.minimizado && !!saved.dismissed
  return { state, dismissed: !!saved.dismissed, minimizado }
}

/** Text of the thin bar left when the stepper is minimized: how many questions and where you are. */
export function minLabel(qs: Opciones[], s: StepperState): string {
  const n = qs.length
  if (n <= 1) return 'Pregunta pendiente · tocá para responder'
  if (isSummary(n, s)) return `Preguntas · ${n} de ${n} · tocá para enviar`
  return `Preguntas · ${Math.min(n, s.step + 1)} de ${n} · tocá para seguir`
}

// ---------- keyboard ----------

export type StepperKey = { type: 'pick'; i: number } | { type: 'enter' } | { type: 'back' } | { type: 'forward' } | { type: 'escape' } | { type: 'minimize' }

export interface KeyLike {
  key: string
  shiftKey?: boolean
  altKey?: boolean
  ctrlKey?: boolean
  metaKey?: boolean
  isComposing?: boolean
}

/** What a key does in the stepper; `typing` is true while the free-text field has focus. */
export function stepperKey(e: KeyLike, typing: boolean, minimizar: string = 'm'): StepperKey | null {
  if (e.isComposing) return null
  if (!typing && coincide(e, minimizar)) return { type: 'minimize' }
  if (e.ctrlKey || e.metaKey || e.altKey) return null
  if (e.key === 'Escape') return { type: 'escape' }
  if (e.key === 'Enter') return e.shiftKey ? null : { type: 'enter' }
  if (typing) return null
  if (/^[1-6]$/.test(e.key)) return { type: 'pick', i: Number(e.key) - 1 }
  if (e.key === 'ArrowLeft' || e.key === 'Backspace') return { type: 'back' }
  if (e.key === 'ArrowRight') return { type: 'forward' }
  return null
}

// ---------- persistence ----------

const KEY = 'orq.preguntas'
const MAX_CHATS = 40

function readAll(): Record<string, Progreso> {
  try {
    const raw = localStorage.getItem(KEY)
    const v = raw ? JSON.parse(raw) : {}
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {}
  } catch {
    return {}
  }
}

function writeAll(all: Record<string, Progreso>) {
  try {
    const entries = Object.entries(all).sort((a, b) => b[1].at - a[1].at).slice(0, MAX_CHATS)
    localStorage.setItem(KEY, JSON.stringify(Object.fromEntries(entries)))
  } catch {
    /* storage unavailable: progress lives in memory only */
  }
}

const memory = new Map<string, Progreso>()

export function loadProgreso(chat: string): Progreso | null {
  return memory.get(chat) ?? readAll()[chat] ?? null
}

export function saveProgreso(chat: string, p: Omit<Progreso, 'at'>) {
  const full = { ...p, at: Date.now() }
  memory.set(chat, full)
  const all = readAll()
  all[chat] = full
  writeAll(all)
}

export function clearProgreso(chat: string) {
  memory.delete(chat)
  const all = readAll()
  if (!(chat in all)) return
  delete all[chat]
  writeAll(all)
}

export const pendingLabel = (n: number) => (n === 1 ? '1 pregunta pendiente' : `${n} preguntas pendientes`)

/**
 * Whether the dock keeps the plain input instead of the stepper. Only a blocking dialog does: the session
 * may read `working` for any reason (background agents included) and the answer goes out as one more message.
 */
export const dockHold = (s: { working: boolean; blocked: boolean }): boolean => s.blocked
