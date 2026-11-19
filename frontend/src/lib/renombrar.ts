import { superaUmbral } from './geometria'

export const NOMBRE_MAX = 60
export const LONG_PRESS_MS = 500
export const LONG_PRESS_MOVE_PX = 8

const GRUPO_RE = /^g\d+$/
const PESTANA_RE = /^g\d+:t\d+$/

export type TipoRenombrar = 'grupo' | 'pestana'
export interface RenombrarBody {
  tipo: TipoRenombrar
  id: string
  nombre: string
}

/** Solo los grupos del guardián (g1) y no fijados: renombrar un fijado lo desfijaría. */
export function grupoRenombrable(ws: { id: string; pinned?: boolean }): boolean {
  return GRUPO_RE.test(ws.id) && !ws.pinned
}

export function pestanaRenombrable(ws: { id: string; pinned?: boolean }, tab: { id: string }): boolean {
  return grupoRenombrable(ws) && PESTANA_RE.test(tab.id)
}

/** Pedido listo para mandar, o null si el nombre queda vacío o no cambió. */
export function armarRenombrar(tipo: TipoRenombrar, id: string, nuevo: string, actual: string): RenombrarBody | null {
  const nombre = nuevo.trim().slice(0, NOMBRE_MAX).trim()
  if (!nombre || nombre === actual.trim()) return null
  return { tipo, id, nombre }
}

export interface LongPress {
  down(x: number, y: number): void
  move(x: number, y: number): void
  cancel(): void
}

/** Mantener apretado ~500ms; se cancela si el puntero se mueve o se suelta antes. */
export function createLongPress(onDone: () => void, ms = LONG_PRESS_MS, px = LONG_PRESS_MOVE_PX): LongPress {
  let timer: ReturnType<typeof setTimeout> | undefined
  let x0 = 0
  let y0 = 0
  const cancel = () => {
    clearTimeout(timer)
    timer = undefined
  }
  return {
    down(x, y) {
      cancel()
      x0 = x
      y0 = y
      timer = setTimeout(() => {
        timer = undefined
        onDone()
      }, ms)
    },
    move(x, y) {
      if (timer !== undefined && superaUmbral(x0, y0, x, y, px)) cancel()
    },
    cancel,
  }
}

/** Pestaña a renombrar desde el menú: la de la sesión abierta, si no la enfocada, si no la primera. */
export function pestanaActiva<T extends { id: string }>(tabs: T[], abiertaId: string | null, enfocadaId: string | null): T | null {
  return tabs.find((t) => t.id === abiertaId) ?? tabs.find((t) => t.id === enfocadaId) ?? tabs[0] ?? null
}
