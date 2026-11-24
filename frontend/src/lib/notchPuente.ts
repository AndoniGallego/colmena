export const esRutaNotch = (pathname: string) => pathname === '/notch' || pathname === '/notch/'

/** La ventana "Reunión" de la app de Windows carga la ruta del notch con `?vista=reunion`. */
export const esVistaReunion = (search: string) => new URLSearchParams(search).get('vista') === 'reunion'

export const SESION_RE = /^[A-Za-z0-9_.:-]{1,80}$/

export type TipoAvisoPuente = 'te-toca' | 'termino'

declare global {
  interface Window {
    __TAURI__?: {
      core?: { invoke?: (cmd: string, args?: Record<string, unknown>) => Promise<unknown> }
      event?: {
        listen?: (evento: string, cb: (e: unknown) => void) => Promise<unknown>
        emit?: (evento: string, payload?: unknown) => Promise<unknown>
      }
    }
  }
}

export interface Puente {
  enPrograma: boolean
  tamano(ancho: number, alto: number, foco: boolean): void
  forma(x: number, y: number, ancho: number, alto: number, radio: number): void
  arrastrar(): void
  abrirColmena(sessionId?: string | null): void
  /** Abre Colmena directo en un ítem de la Biblioteca (id de 32 hex); con otro id abre Colmena sin ítem. */
  abrirBiblioteca(item: string): void
  aviso(tipo: TipoAvisoPuente): void
  /** Trae al frente la ventana "Reunión" (la abre si hace falta). */
  mostrarReunion(): void
}

const ITEM_BIBLIOTECA = /^[0-9a-f]{32}$/

export const MARGEN_X = 16
export const MARGEN_Y = 16

const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n))

export type RectPastillaForma = { x: number; y: number; ancho: number; alto: number; radio: number }

/** Unión de dos rectángulos lógicos; el radio es el mayor de los dos. */
export function formaPara(a: RectPastillaForma, b?: RectPastillaForma): RectPastillaForma {
  if (!b) {
    return { ...a }
  }
  const x1 = Math.min(a.x, b.x)
  const y1 = Math.min(a.y, b.y)
  const x2 = Math.max(a.x + a.ancho, b.x + b.ancho)
  const y2 = Math.max(a.y + a.alto, b.y + b.alto)
  return {
    x: x1,
    y: y1,
    ancho: x2 - x1,
    alto: y2 - y1,
    radio: Math.max(a.radio, b.radio),
  }
}

export function ventanaPara(pastilla: { ancho: number; alto: number }): { ancho: number; alto: number } {
  return {
    ancho: clamp(Math.ceil(pastilla.ancho) + 2 * MARGEN_X, 120, 800),
    alto: clamp(Math.ceil(pastilla.alto) + MARGEN_Y, 40, 1400),
  }
}

export function pasosVentana(
  actual: { ancho: number; alto: number } | null,
  destino: { ancho: number; alto: number },
): { antes: { ancho: number; alto: number } | null; despues: { ancho: number; alto: number } | null } {
  if (!actual) {
    return { antes: destino, despues: null }
  }
  if (actual.ancho === destino.ancho && actual.alto === destino.alto) {
    return { antes: null, despues: null }
  }
  const gteW = destino.ancho >= actual.ancho
  const gteH = destino.alto >= actual.alto
  const lteW = destino.ancho <= actual.ancho
  const lteH = destino.alto <= actual.alto
  if (gteW && gteH) {
    return { antes: destino, despues: null }
  }
  if (lteW && lteH) {
    return { antes: null, despues: destino }
  }
  return {
    antes: { ancho: Math.max(actual.ancho, destino.ancho), alto: Math.max(actual.alto, destino.alto) },
    despues: destino,
  }
}

function sesionValida(id?: string | null): string | null {
  if (typeof id !== 'string' || !SESION_RE.test(id)) return null
  return id
}

/** Escucha un evento de la app de Windows; no hace nada fuera del programa. */
export function escuchar(evento: string, cb: () => void, w: Window = window): Promise<boolean> {
  const listen = w.__TAURI__?.event?.listen
  if (typeof listen !== 'function') return Promise.resolve(false)
  return listen(evento, () => cb()).then(
    () => true,
    () => false,
  )
}

/** Avisa a la app de Windows; no hace nada fuera del programa. */
export function emitir(evento: string, w: Window = window): void {
  const emit = w.__TAURI__?.event?.emit
  if (typeof emit !== 'function') return
  emit(evento).catch(() => undefined)
}

export function crearPuente(w: Window = window): Puente {
  const invoke = w.__TAURI__?.core?.invoke
  const enPrograma = typeof invoke === 'function'

  return {
    enPrograma,
    tamano(ancho, alto, foco) {
      if (!enPrograma) return
      invoke!('notch_tamano', { ancho, alto, foco }).catch(() => undefined)
    },
    forma(x, y, ancho, alto, radio) {
      if (!enPrograma) return
      invoke!('notch_forma', { x, y, ancho, alto, radio }).catch(() => undefined)
    },
    arrastrar() {
      if (!enPrograma) return
      invoke!('notch_arrastrar').catch(() => undefined)
    },
    abrirColmena(sessionId) {
      const sesion = sesionValida(sessionId)
      if (enPrograma) {
        invoke!('abrir_colmena', { sesion }).catch(() => undefined)
        return
      }
      w.open(sesion ? '/?session=' + encodeURIComponent(sesion) : '/', 'colmena')
    },
    abrirBiblioteca(item) {
      if (!ITEM_BIBLIOTECA.test(item)) {
        this.abrirColmena(null)
        return
      }
      if (enPrograma) {
        invoke!('abrir_biblioteca', { item }).catch(() => undefined)
        return
      }
      w.open('/?biblioteca=' + item, 'colmena')
    },
    aviso(tipo) {
      if (!enPrograma) return
      invoke!('mostrar_aviso', { tipo }).catch(() => undefined)
    },
    mostrarReunion() {
      if (!enPrograma) return
      invoke!('reunion_mostrar_ventana').catch(() => undefined)
    },
  }
}
