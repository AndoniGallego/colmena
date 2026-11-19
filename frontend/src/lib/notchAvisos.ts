import type { Aviso } from '../api/types'
import type { ModoNotch } from './notchMovimiento'

export type KindNotch = 'asks' | 'blocked' | 'done' | 'pestana'

export interface AvisoNotch {
  id: number
  kind: KindNotch
  titulo: string
  cuerpo: string
  session_id: string
  pedido?: string
}

export const DURACION_TERMINO_S = 4.5
export const MAX_ESPERA_TERMINO_MS = 30_000

const SUFIJO: Record<KindNotch, string> = {
  done: ' terminó',
  asks: ' te pregunta',
  blocked: ' espera una aprobación',
  pestana: '',
}

/** Nombre de la sesión sin el verbo del título del backend; si no matchea, el título entero. */
export function nombreAviso(titulo: string, kind: KindNotch): string {
  const sufijo = SUFIJO[kind]
  if (!titulo.endsWith(sufijo)) return titulo
  const nombre = titulo.slice(0, -sufijo.length)
  if (nombre.trim() === '') return titulo
  return nombre
}

export const ETIQUETA_AVISO: Record<KindNotch, string> = {
  done: 'Terminó',
  asks: 'Te pregunta',
  blocked: 'Espera tu aprobación',
  pestana: 'Pedido de pestaña',
}

export const BRILLO_AVISO_KIND: Record<KindNotch, string> = {
  done: 'var(--st-done)',
  asks: 'var(--st-working)',
  blocked: 'var(--st-blocked)',
  pestana: 'var(--accent)',
}

export function brilloPillDesdeAviso(
  auth: string,
  modo: ModoNotch,
  aviso: AvisoNotch | null | undefined,
): string | null {
  if (auth !== 'ready' || modo !== 'aviso' || !aviso) return null
  return BRILLO_AVISO_KIND[aviso.kind]
}

/** Tiempo restante hasta el cierre automático de un aviso done (ms), sin bajar de cero. */
export function msRestanteCierreDone(deadlineMs: number, ahoraMs: number): number {
  return Math.max(0, deadlineMs - ahoraMs)
}

/** Click en .main del aviso simple: session_id a emitir en abrir-sesion, o null si no hay id. */
export function abrirSesionDesdeAvisoSimple(session_id: string): string | null {
  const sid = session_id.trim()
  return sid ? sid : null
}

export type TweenCierreDone = { pause(): void; resume(): void; kill(): void }

export type ControlCierreDone = {
  pointerEnter(): void
  pointerLeave(): void
  dispose(): void
}

type CrearControlCierreDoneOpts = {
  duracionMs: number
  /** Extra sobre el restante para el setTimeout de respaldo (p. ej. 100 fuera de soft). */
  margenTimeoutMs: number
  now: () => number
  onCerrar: () => void
  schedule: (fn: () => void, ms: number) => ReturnType<typeof setTimeout>
  cancel: (id: ReturnType<typeof setTimeout> | null) => void
  crearTween?: () => TweenCierreDone | null
}

/** Temporizador de cierre de aviso done, pausable con pointer enter/leave. */
export function crearControlCierreDone(opts: CrearControlCierreDoneOpts): ControlCierreDone {
  let deadlineMs = opts.now() + opts.duracionMs
  let restanteAlPausarMs = 0
  let pausado = false
  let cerrado = false
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let tween: TweenCierreDone | null = opts.crearTween?.() ?? null

  const emitCerrar = () => {
    if (cerrado) return
    cerrado = true
    if (timeoutId != null) {
      opts.cancel(timeoutId)
      timeoutId = null
    }
    tween?.kill()
    tween = null
    opts.onCerrar()
  }

  const programar = (ms: number) => {
    if (timeoutId != null) {
      opts.cancel(timeoutId)
      timeoutId = null
    }
    if (ms <= 0) {
      emitCerrar()
      return
    }
    timeoutId = opts.schedule(() => emitCerrar(), ms)
  }

  programar(opts.duracionMs + opts.margenTimeoutMs)

  return {
    pointerEnter() {
      if (pausado || cerrado) return
      pausado = true
      restanteAlPausarMs = msRestanteCierreDone(deadlineMs, opts.now())
      if (timeoutId != null) {
        opts.cancel(timeoutId)
        timeoutId = null
      }
      tween?.pause()
    },
    pointerLeave() {
      if (!pausado || cerrado) return
      pausado = false
      deadlineMs = opts.now() + restanteAlPausarMs
      programar(restanteAlPausarMs + opts.margenTimeoutMs)
      tween?.resume()
    },
    dispose() {
      if (timeoutId != null) {
        opts.cancel(timeoutId)
        timeoutId = null
      }
      tween?.kill()
      tween = null
    },
  }
}

const KINDS: ReadonlySet<string> = new Set(['asks', 'blocked', 'done', 'pestana'])

function esKindNotch(k: string): k is KindNotch {
  return KINDS.has(k)
}

export function nuevosParaNotch(items: Aviso[], desde: number): AvisoNotch[] {
  return items
    .filter((a) => esKindNotch(a.kind) && a.id > desde)
    .sort((a, b) => a.id - b.id)
    .map((a) => ({
      id: a.id,
      kind: a.kind as KindNotch,
      titulo: a.titulo,
      cuerpo: a.cuerpo,
      session_id: a.session_id,
      ...(a.pedido ? { pedido: a.pedido } : {}),
    }))
}

export function maxId(items: Aviso[]): number {
  let m = 0
  for (const a of items) if (a.id > m) m = a.id
  return m
}

export const esTeTocaAviso = (a: AvisoNotch): boolean => a.kind !== 'done'

export const esPedidoPestanaNotch = (a: AvisoNotch): boolean => a.kind === 'pestana'

export type OpcionesSiguienteAviso = {
  ahora?: number
  llegada?: (a: AvisoNotch) => number | undefined
  mostrando?: AvisoNotch | null
}

function teTocaSaltear(
  a: AvisoNotch,
  teToca: ReadonlySet<string>,
  resuelto?: (a: AvisoNotch) => boolean,
): boolean {
  if (!esTeTocaAviso(a)) return false
  return resuelto ? resuelto(a) : !teToca.has(a.session_id)
}

function teTocaVigente(
  a: AvisoNotch,
  teToca: ReadonlySet<string>,
  resuelto?: (a: AvisoNotch) => boolean,
): boolean {
  return esTeTocaAviso(a) && !teTocaSaltear(a, teToca, resuelto)
}

function hayTeTocaMismaSesion(
  session_id: string,
  cola: AvisoNotch[],
  mostrando: AvisoNotch | null,
  teToca: ReadonlySet<string>,
  resuelto?: (a: AvisoNotch) => boolean,
): boolean {
  if (mostrando && teTocaVigente(mostrando, teToca, resuelto) && mostrando.session_id === session_id) {
    return true
  }
  return cola.some((a) => teTocaVigente(a, teToca, resuelto) && a.session_id === session_id)
}

function doneVencido(
  a: AvisoNotch,
  ahora: number,
  llegada?: (a: AvisoNotch) => number | undefined,
): boolean {
  if (!llegada) return false
  const t = llegada(a)
  if (t === undefined) return false
  return ahora - t > MAX_ESPERA_TERMINO_MS
}

export function siguienteAviso(
  cola: AvisoNotch[],
  teToca: ReadonlySet<string>,
  resuelto?: (a: AvisoNotch) => boolean,
  opciones?: OpcionesSiguienteAviso,
): { aviso: AvisoNotch | null; resto: AvisoNotch[]; descartados: AvisoNotch[] } {
  const ahora = opciones?.ahora ?? Date.now()
  const llegada = opciones?.llegada
  const mostrando = opciones?.mostrando ?? null

  const descartados: AvisoNotch[] = []
  const pendientes: AvisoNotch[] = []

  for (const a of cola) {
    if (teTocaSaltear(a, teToca, resuelto)) {
      descartados.push(a)
      continue
    }
    if (!esTeTocaAviso(a)) {
      if (hayTeTocaMismaSesion(a.session_id, cola, mostrando, teToca, resuelto)) {
        descartados.push(a)
        continue
      }
      if (doneVencido(a, ahora, llegada)) {
        descartados.push(a)
        continue
      }
    }
    pendientes.push(a)
  }

  const avisoTeToca = pendientes.find((a) => esTeTocaAviso(a))
  if (avisoTeToca) {
    const resto = pendientes.filter((a) => a.id !== avisoTeToca.id)
    return { aviso: avisoTeToca, resto, descartados }
  }

  const dones = pendientes.filter((a) => !esTeTocaAviso(a))
  if (!dones.length) return { aviso: null, resto: [], descartados }

  dones.sort((a, b) => {
    const la = llegada?.(a) ?? a.id
    const lb = llegada?.(b) ?? b.id
    return la - lb
  })
  const aviso = dones[0]!
  const resto = pendientes.filter((a) => a.id !== aviso.id)
  return { aviso, resto, descartados }
}

/** Si se muestra un done y llega te-toca vigente de la misma sesión, devuelve el aviso que lo reemplaza. */
export function debeReemplazarAvisoActual(
  actual: AvisoNotch | null,
  nuevos: AvisoNotch[],
  teToca: ReadonlySet<string>,
  resuelto?: (a: AvisoNotch) => boolean,
): AvisoNotch | null {
  if (!actual || esTeTocaAviso(actual)) return null
  const sid = actual.session_id
  for (const a of nuevos) {
    if (a.session_id === sid && teTocaVigente(a, teToca, resuelto)) return a
  }
  return null
}
