export const MAX_TEXTO = 4000
export const BLOCKED_REPLY = 'Está esperando una aprobación en la terminal'

export function textoProblem(texto: string): string | null {
  const n = texto.trim().length
  if (n === 0) return 'Escribí el mensaje'
  return n > MAX_TEXTO ? `Máximo ${MAX_TEXTO} caracteres (van ${n})` : null
}

/** A message may be only attachments; the server fills in the wording. */
export const replyProblem = (texto: string, files: number): string | null => (files > 0 && !texto.trim() ? null : textoProblem(texto))

interface KeyLike {
  key: string
  shiftKey: boolean
  isComposing: boolean
}

/**
 * Enter sends on desktop; on touch it stays a line break and the button sends. While the session
 * works the big key is the brake, so on touch the keyboard's Enter is the way to queue.
 */
export const enterSends = (e: KeyLike, finePointer: boolean, working = false) =>
  (finePointer || working) && e.key === 'Enter' && !e.shiftKey && !e.isComposing

/** randomUUID only exists in secure contexts; the app is also reachable over plain http on the LAN. */
export function newId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
}

export interface ComposerKeyInput {
  working: boolean
  blocked: boolean
  texto: string
  files: number
}

/**
 * Mientras la sesión trabaja y no hay nada escrito la tecla grande frena; apenas escribís o adjuntás
 * vuelve a ser Enter y lo escrito se encola. Esperando aprobación no se frena desde acá.
 */
export function composerKeys(p: ComposerKeyInput): { key: 'stop' | 'send'; queues: boolean } {
  const queues = p.working && !p.blocked
  const empty = !p.texto.trim() && p.files === 0
  return { key: queues && empty ? 'stop' : 'send', queues }
}
