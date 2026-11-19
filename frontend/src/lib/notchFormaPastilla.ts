import type { RectPastillaForma } from './notchPuente'

/** Holgura lógica (px) por lado al informar la región al shell; 0 = ancho/alto = caja de la pastilla. */
export const FORMA_HOLGURA_LADO = 0

/**
 * Rect de destino para la forma: pastilla centrada en el ancho útil (viewport), con scroll documental.
 * `extraAnchoRender` compensa borde/subpixel: típicamente `getBoundingClientRect().width - parseFloat(getComputedStyle(el).width)`.
 */
export function rectDestinoCentrado(
  anchoVentana: number,
  anchoCss: number,
  alto: number,
  radio: number,
  extraAnchoRender: number,
  scrollX: number,
  scrollY: number,
  holguraPorLado: number = FORMA_HOLGURA_LADO,
): RectPastillaForma {
  const anchoRender = anchoCss + Math.max(0, extraAnchoRender)
  const xCentro = (anchoVentana - anchoRender) / 2 + scrollX - holguraPorLado
  const y = scrollY - holguraPorLado
  return {
    x: xCentro,
    y,
    ancho: anchoRender + 2 * holguraPorLado,
    alto: alto + 2 * holguraPorLado,
    radio,
  }
}

/** Rect lógico de la pastilla respecto a la ventana (scroll incluido), mismo alto que la caja. */
export function rectFormaDesdeCaja(
  box: { left: number; top: number },
  ancho: number,
  alto: number,
  radio: number,
  scrollX: number,
  scrollY: number,
): RectPastillaForma {
  return {
    x: box.left + scrollX,
    y: box.top + scrollY,
    ancho,
    alto,
    radio,
  }
}

/**
 * Recorta coordenadas negativas hacia el origen (misma semántica que el núcleo):
 * si x o y < 0, se pone en 0 y se reduce ancho/alto en lo recortado.
 */
export function ajustarFormaAVentana(rect: RectPastillaForma): RectPastillaForma {
  let { x, y, ancho, alto, radio } = rect
  if (x < 0) {
    ancho += x
    x = 0
  }
  if (y < 0) {
    alto += y
    y = 0
  }
  return { x, y, ancho, alto, radio }
}

/**
 * Encoge el rect 1 px físico hacia adentro en cada eje (excepto el borde superior si y≤0),
 * para que el borde de la región del núcleo caiga sobre la parte opaca de la pastilla.
 *
 * Los bordes lógicos se devuelven con 0,25 px físico hacia adentro del píxel límite
 * (p. ej. x = (izq + 0.25) / s) para que floor/ceil al multiplicar por dpr coincidan
 * con izq/der/arr/ab y no fallen por errores ε de coma flotante.
 */
export function encogerFormaAPixeles(rect: RectPastillaForma, dpr: number): RectPastillaForma {
  const s = Number.isFinite(dpr) && dpr > 0 ? dpr : 1
  const { x, y, ancho, alto, radio } = rect

  const izq = Math.ceil(x * s) + 1
  const der = Math.floor((x + ancho) * s) - 1
  const arr = y <= 0 ? 0 : Math.ceil(y * s) + 1
  const ab = Math.floor((y + alto) * s) - 1

  const wPx = der - izq
  const hPx = ab - arr
  if (wPx <= 0 || hPx <= 0) {
    return { ...rect }
  }

  const xNew = (izq + 0.25) / s
  const yNew = arr <= 0 ? 0 : (arr + 0.25) / s
  const anchoNew = (der - 0.25) / s - xNew
  const altoNew = (ab - 0.25) / s - yNew

  return {
    x: xNew,
    y: yNew,
    ancho: anchoNew,
    alto: altoNew,
    radio: Math.max(0, radio - 1 / s),
  }
}
