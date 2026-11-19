import { describe, expect, it } from 'vitest'
import { ajustarFormaAVentana, encogerFormaAPixeles, rectDestinoCentrado } from './notchFormaPastilla'
import { formaPara, type RectPastillaForma } from './notchPuente'

function contains(a: RectPastillaForma, b: RectPastillaForma): boolean {
  const ax2 = a.x + a.ancho
  const ay2 = a.y + a.alto
  const bx2 = b.x + b.ancho
  const by2 = b.y + b.alto
  return a.x <= b.x + 1e-6 && a.y <= b.y + 1e-6 && ax2 >= bx2 - 1e-6 && ay2 >= by2 - 1e-6
}

describe('rectDestinoCentrado', () => {
  const anchoVentana = 800
  const alto = 100
  const radio = 22
  const extra = 2
  const scrollX = 0
  const scrollY = 0

  it('cuando crece el ancho CSS, x del rect destino disminuye', () => {
    const estrecho = rectDestinoCentrado(anchoVentana, 200, alto, radio, extra, scrollX, scrollY)
    const ancho = rectDestinoCentrado(anchoVentana, 400, alto, radio, extra, scrollX, scrollY)
    expect(ancho.x).toBeLessThan(estrecho.x)
  })

  it('cuando achica el ancho CSS, x del rect destino aumenta', () => {
    const ancho = rectDestinoCentrado(anchoVentana, 400, alto, radio, extra, scrollX, scrollY)
    const estrecho = rectDestinoCentrado(anchoVentana, 200, alto, radio, extra, scrollX, scrollY)
    expect(estrecho.x).toBeGreaterThan(ancho.x)
  })

  it('la unión con el rect actual contiene destino y actual', () => {
    const anchoCss = 300
    const dest = rectDestinoCentrado(anchoVentana, anchoCss, alto, radio, extra, scrollX, scrollY)
    const cur: RectPastillaForma = {
      x: 250,
      y: 0,
      ancho: 200,
      alto,
      radio: 20,
    }
    const u = formaPara(dest, cur)
    expect(contains(u, dest)).toBe(true)
    expect(contains(u, cur)).toBe(true)
  })

  it('centra usando ancho de render (CSS + extra)', () => {
    const anchoCss = 200
    const r = rectDestinoCentrado(anchoVentana, anchoCss, alto, radio, 2, 0, 0)
    const anchoRender = anchoCss + 2
    const esperadoX = (anchoVentana - anchoRender) / 2
    expect(r.x).toBeCloseTo(esperadoX, 5)
    expect(r.ancho).toBeCloseTo(anchoRender, 5)
  })
})

describe('ajustarFormaAVentana', () => {
  const base = { x: 0, y: 0, ancho: 100, alto: 50, radio: 22 }

  it('y=-1 recorta arriba y resta 1 al alto', () => {
    expect(ajustarFormaAVentana({ ...base, y: -1 })).toEqual({ ...base, y: 0, alto: 49 })
  })

  it('x=-3 recorta izquierda y resta 3 al ancho', () => {
    expect(ajustarFormaAVentana({ ...base, x: -3 })).toEqual({ ...base, x: 0, ancho: 97 })
  })
})

/**
 * El rect encogido debe coincidir en px físicos con la región desplazada 1px dentro del original
 * (mismos bordes que usaría el núcleo si pasara esos límites enteros).
 */
function nucleoCoincideForma(base: RectPastillaForma, r: RectPastillaForma, s: number): boolean {
  const izqEsp = Math.ceil(base.x * s) + 1
  const derEsp = Math.floor((base.x + base.ancho) * s) - 1
  const arrEsp = base.y <= 0 ? 0 : Math.ceil(base.y * s) + 1
  const abEsp = Math.floor((base.y + base.alto) * s) - 1
  return (
    Math.floor(r.x * s) === izqEsp &&
    Math.ceil((r.x + r.ancho) * s) === derEsp &&
    Math.floor(r.y * s) === arrEsp &&
    Math.ceil((r.y + r.alto) * s) === abEsp
  )
}

describe('encogerFormaAPixeles', () => {
  it('x fraccionaria 100.5 y dpr 1: izquierda lógica 102 y coincide con núcleo', () => {
    const base = { x: 100.5, y: 0, ancho: 200, alto: 50, radio: 22 }
    const s = 1
    const r = encogerFormaAPixeles(base, s)
    expect(r.x).toBe(102.25)
    expect(r.y).toBe(0)
    expect(r.ancho).toBe(196.5)
    expect(r.alto).toBe(48.75)
    expect(r.radio).toBe(21)
    expect(nucleoCoincideForma(base, r, s)).toBe(true)
  })

  it('con y=0 no encoge el borde superior (arr físico 0)', () => {
    const base = { x: 10, y: 0, ancho: 100, alto: 40, radio: 12 }
    const r = encogerFormaAPixeles(base, 1)
    expect(r.y).toBe(0)
    expect(Math.floor(r.y * 1)).toBe(0)
  })

  it('con y>0 encoge arriba un px físico', () => {
    const base = { x: 0, y: 2, ancho: 100, alto: 48, radio: 10 }
    const s = 1
    const r = encogerFormaAPixeles(base, s)
    expect(Math.floor(r.y * s)).toBe(Math.ceil(2 * s) + 1)
    expect(nucleoCoincideForma(base, r, s)).toBe(true)
  })

  it('dpr 1.25: invariantes núcleo e izq/der esperados', () => {
    const base = { x: 100.5, y: 0, ancho: 200, alto: 50, radio: 15 }
    const s = 1.25
    const r = encogerFormaAPixeles(base, s)
    const izq = Math.ceil(100.5 * s) + 1
    const der = Math.floor((100.5 + 200) * s) - 1
    expect(Math.floor(r.x * s)).toBe(izq)
    expect(Math.ceil((r.x + r.ancho) * s)).toBe(der)
    expect(nucleoCoincideForma(base, r, s)).toBe(true)
    expect(r.radio).toBeCloseTo(15 - 1 / s, 10)
  })

  it('dpr 1.5: invariantes núcleo', () => {
    const base = { x: 50.25, y: 1, ancho: 120, alto: 36, radio: 18 }
    const s = 1.5
    const r = encogerFormaAPixeles(base, s)
    expect(nucleoCoincideForma(base, r, s)).toBe(true)
  })

  it('rect diminuto: ancho o alto no positivos en px físicos → sin cambios', () => {
    const peque = { x: 0, y: 0, ancho: 2, alto: 2, radio: 4 }
    expect(encogerFormaAPixeles(peque, 1)).toEqual(peque)
  })

  it('dpr inválido (NaN o ≤0) se trata como 1', () => {
    const base = { x: 10.5, y: 0, ancho: 100, alto: 40, radio: 12 }
    const esperado = encogerFormaAPixeles(base, 1)
    expect(encogerFormaAPixeles(base, NaN)).toEqual(esperado)
    expect(encogerFormaAPixeles(base, 0)).toEqual(esperado)
    expect(encogerFormaAPixeles(base, -2)).toEqual(esperado)
  })

  /**
   * Simula el núcleo Rust: bordes en px físicos deben coincidir con ceil/floor de la región encogida * s.
   * Barre dpr fraccionarios y muchas fracciones de x/ancho (fallaba antes en 1.75 por ε en coma flotante).
   */
  it('simulación núcleo: floor/ceil de rect * dpr = límites esperados para muchos dpr y rect fraccionarios', () => {
    const dprs = [1, 1.25, 1.5, 1.75, 2, 2.25, 3]
    const radio = 20
    const yCasos = [0, 0.33, 1.7, 12.456]
    for (const s of dprs) {
      for (let paso = 0; paso <= 3000; paso += 1) {
        const x = paso * 0.1
        const base: RectPastillaForma = {
          x,
          y: 0,
          ancho: 180.3,
          alto: 90.7,
          radio,
        }
        const izq = Math.ceil(base.x * s) + 1
        const der = Math.floor((base.x + base.ancho) * s) - 1
        const arr = base.y <= 0 ? 0 : Math.ceil(base.y * s) + 1
        const ab = Math.floor((base.y + base.alto) * s) - 1
        if (der - izq <= 0 || ab - arr <= 0) continue
        const r = encogerFormaAPixeles(base, s)
        expect(Math.floor(r.x * s), `x=${x} s=${s}`).toBe(izq)
        expect(Math.ceil((r.x + r.ancho) * s), `x=${x} s=${s}`).toBe(der)
        expect(Math.floor(r.y * s)).toBe(arr)
        expect(Math.ceil((r.y + r.alto) * s)).toBe(ab)
      }
      for (const y of yCasos) {
        for (let paso = 0; paso <= 500; paso += 1) {
          const x = paso * 0.07 + 0.03
          const base: RectPastillaForma = {
            x,
            y,
            ancho: 133.333,
            alto: 77.777,
            radio,
          }
          const izq = Math.ceil(base.x * s) + 1
          const der = Math.floor((base.x + base.ancho) * s) - 1
          const arr = base.y <= 0 ? 0 : Math.ceil(base.y * s) + 1
          const ab = Math.floor((base.y + base.alto) * s) - 1
          if (der - izq <= 0 || ab - arr <= 0) continue
          const r = encogerFormaAPixeles(base, s)
          expect(Math.floor(r.x * s), `x=${x} y=${y} s=${s}`).toBe(izq)
          expect(Math.ceil((r.x + r.ancho) * s), `x=${x} y=${y} s=${s}`).toBe(der)
          expect(Math.floor(r.y * s), `x=${x} y=${y} s=${s}`).toBe(arr)
          expect(Math.ceil((r.y + r.alto) * s), `x=${x} y=${y} s=${s}`).toBe(ab)
        }
      }
    }
  })
})
