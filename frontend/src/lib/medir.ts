import { ref } from 'vue'
import { medirAprox, type Medir } from './escena'

let ctx: CanvasRenderingContext2D | null | undefined
const cache = new Map<string, number>()

/** Bumps once the web font is in, so layouts measured with the fallback font get redone. */
export const fuentes = ref(0)

if (typeof document !== 'undefined' && document.fonts?.ready) {
  document.fonts.ready.then(() => {
    cache.clear()
    fuentes.value++
  })
}

/** Measures with the real UI font on a canvas; falls back to the estimate where there is no canvas (tests, old browsers). */
export const medirTexto: Medir = (texto, px, peso = 400) => {
  if (ctx === undefined) {
    try {
      ctx = typeof document !== 'undefined' ? document.createElement('canvas').getContext('2d') : null
    } catch {
      ctx = null
    }
  }
  if (!ctx) return medirAprox(texto, px, peso)
  const k = `${peso}|${px}|${texto}`
  let w = cache.get(k)
  if (w === undefined) {
    ctx.font = `${peso} ${px}px "Instrument Sans Variable", "Instrument Sans", system-ui, sans-serif`
    // a hair of slack so the SVG text never touches its box edge
    w = ctx.measureText(texto).width * 1.03 + 0.5
    if (cache.size > 4000) cache.clear()
    cache.set(k, w)
  }
  return w
}
