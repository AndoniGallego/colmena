import { ApiError, type TipoNota } from '../api/types'

/** Notas que el notch no pudo mandar por falta de red; se reintentan al reconectar. */
export type NotaEnCola = { tipo: TipoNota; texto: string }
type Entrada = NotaEnCola & { id: string }

const CLAVE = 'colmena.notas.cola'
/** Si localStorage no anda, la cola vive en memoria: no se pierde en silencio mientras el notch siga abierto. */
let memoria: Entrada[] = []
let vaciando: Promise<number> | null = null

function valida(x: unknown): x is Entrada {
  if (!x || typeof x !== 'object') return false
  const e = x as Record<string, unknown>
  return (
    typeof e.id === 'string' &&
    typeof e.texto === 'string' &&
    (e.tipo === 'recordatorio' || e.tipo === 'apunte')
  )
}

function leer(): Entrada[] {
  try {
    const raw = localStorage.getItem(CLAVE)
    if (raw === null) return memoria
    const lista: unknown = JSON.parse(raw)
    return Array.isArray(lista) ? lista.filter(valida) : []
  } catch {
    return memoria
  }
}

function escribir(lista: Entrada[]): void {
  memoria = lista
  try {
    if (lista.length) localStorage.setItem(CLAVE, JSON.stringify(lista))
    else localStorage.removeItem(CLAVE)
  } catch {
    /* sin localStorage: queda en memoria */
  }
}

function nuevoId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function encolar(b: NotaEnCola): void {
  escribir([...leer(), { id: nuevoId(), tipo: b.tipo, texto: b.texto }])
}

export function pendientesCola(): number {
  return leer().length
}

/**
 * Manda las notas en orden, de a una, y saca cada una apenas se guardó. Frena en el primer fallo
 * para reintentar después. Si ya hay un vaciado en curso, devuelve ese (ninguna se manda dos veces).
 */
export function vaciarCola(crear: (b: NotaEnCola) => Promise<unknown>): Promise<number> {
  if (vaciando) return vaciando
  vaciando = (async () => {
    let enviadas = 0
    try {
      for (;;) {
        const primera = leer()[0]
        if (!primera) break
        try {
          await crear({ tipo: primera.tipo, texto: primera.texto })
        } catch {
          break
        }
        escribir(leer().filter((e) => e.id !== primera.id))
        enviadas++
      }
    } finally {
      vaciando = null
    }
    return enviadas
  })()
  return vaciando
}

/** Gateways que responden cuando el orquestador de atrás no está. */
const SIN_ORQUESTADOR = new Set([502, 503, 504])

/** El pedido no llegó al orquestador (sin red o caído), a diferencia de un error que respondió el servidor. */
export function esSinRed(e: unknown): boolean {
  if (e instanceof ApiError) return SIN_ORQUESTADOR.has(e.status)
  if (e instanceof TypeError) return true
  const msg = e instanceof Error ? e.message : String(e)
  return msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('Load failed')
}
