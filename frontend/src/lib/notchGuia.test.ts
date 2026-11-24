import { describe, expect, it } from 'vitest'
import { CIERRE_GUIA_MS, guiaMontada } from './notchGuia'

describe('guiaMontada', () => {
  it('en modo guía la cajita está montada', () => {
    expect(guiaMontada('guia', 'cerrado', false)).toEqual({ visible: true, quitarEn: null })
  })

  it('al cerrarse desde la guía sigue montada un rato para animar la salida', () => {
    expect(guiaMontada('cerrado', 'guia', true)).toEqual({ visible: true, quitarEn: CIERRE_GUIA_MS })
  })

  it('al pasar a otro modo se va enseguida', () => {
    expect(guiaMontada('panel', 'guia', true)).toEqual({ visible: false, quitarEn: null })
    expect(guiaMontada('notas', 'cerrado', true)).toEqual({ visible: false, quitarEn: null })
  })

  it('cerrado sin venir de la guía no la monta', () => {
    expect(guiaMontada('cerrado', 'panel', false)).toEqual({ visible: false, quitarEn: null })
  })

  it('la espera alcanza para la salida y es acotada', () => {
    expect(CIERRE_GUIA_MS).toBeGreaterThanOrEqual(200)
    expect(CIERRE_GUIA_MS).toBeLessThanOrEqual(800)
  })
})
