import type { ModoNotch } from './notchMovimiento'

/** Lo que la cajita de la guía sigue montada al cerrarse: anima su salida mientras la pastilla se achica. */
export const CIERRE_GUIA_MS = 400

/**
 * Si la cajita de la guía está montada tras un cambio de modo. Al cerrarse desde la guía queda un rato
 * (`quitarEn` ms) para que se vea la salida; a cualquier otro modo se va enseguida.
 */
export function guiaMontada(
  modo: ModoNotch,
  anterior: ModoNotch | undefined,
  visible: boolean,
): { visible: boolean; quitarEn: number | null } {
  if (modo === 'guia') return { visible: true, quitarEn: null }
  if (modo === 'cerrado' && anterior === 'guia' && visible) return { visible: true, quitarEn: CIERRE_GUIA_MS }
  return { visible: false, quitarEn: null }
}
