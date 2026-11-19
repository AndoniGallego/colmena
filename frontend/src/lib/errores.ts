import { ApiError } from '../api/types'

export class ErrorUsuario extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ErrorUsuario'
  }
}

const SESION = 'Tu sesión venció. Volvé a entrar.'
const SIN_RED = 'No llego a Colmena. Revisá la conexión y probá de nuevo.'
const SERVIDOR = 'Colmena tuvo un problema. Probá de nuevo.'
const NO_ENCONTRE = 'No encontré eso. Puede que ya no exista.'
const TARDE = 'Tardó demasiado en responder. Probá de nuevo.'
const MUCHOS = 'Demasiados pedidos seguidos. Esperá un momento y probá de nuevo.'
const GENERICO = 'Algo salió mal. Probá de nuevo.'

function msgDe(e: unknown): string {
  if (typeof e === 'string') return e
  if (e instanceof Error) return e.message
  return String(e)
}

function esTimeout(e: unknown, msg: string): boolean {
  if (e instanceof ApiError && e.status === 408) return true
  if (e instanceof DOMException && (e.name === 'AbortError' || e.name === 'TimeoutError')) return true
  if (e instanceof Error && (e.name === 'AbortError' || e.name === 'TimeoutError')) return true
  const low = msg.toLowerCase()
  return low.includes('timeout') || low.includes('timed out')
}

function esFalloRed(e: unknown, msg: string): boolean {
  if (e instanceof TypeError) return true
  return msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('Load failed')
}

export function mensajeError(e: unknown, fallback?: string): string {
  const fin = () => fallback ?? GENERICO

  if (e instanceof ErrorUsuario) return e.message

  if (e instanceof ApiError) {
    if (e.status === 401 || e.status === 403) return SESION
    if (e.status === 404 && e.sinCuerpo) return NO_ENCONTRE
    if (esTimeout(e, e.detail)) return TARDE
    if (e.status === 429) return MUCHOS
    if (e.status >= 500) return SERVIDOR
    if (e.sinCuerpo) return fin()
    return e.detail
  }

  const msg = msgDe(e)
  if (esTimeout(e, msg)) return TARDE
  if (esFalloRed(e, msg)) return SIN_RED

  return fin()
}

export function detalleTecnico(e: unknown): string | null {
  const mostrado = mensajeError(e)
  if (e instanceof ErrorUsuario) return null
  if (e instanceof ApiError) {
    if (!e.sinCuerpo && mostrado === e.detail) return null
    return `${e.status}: ${e.detail}`
  }
  if (e instanceof Error) {
    if (mostrado === e.message) return null
    return `${e.name}: ${e.message}`
  }
  const raw = String(e)
  if (mostrado === raw) return null
  return raw
}

export const mensajeErrorRed = mensajeError
