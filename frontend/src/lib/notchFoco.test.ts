import { describe, expect, it } from 'vitest'
import { cerrarTrasBlur, claveAvisoNotch, debeCerrarPanelAlPerderFoco, GRACIA_BLUR_MS, reducirFocoNotch } from './notchFoco'

describe('reducirFocoNotch', () => {
  it('tras interacción (foco true), blur lo baja', () => {
    expect(reducirFocoNotch(true, { tipo: 'blur' })).toBe(false)
  })

  it("pasar a 'cerrado' lo baja", () => {
    expect(reducirFocoNotch(true, { tipo: 'modo_cambio', modo: 'cerrado' })).toBe(false)
    expect(reducirFocoNotch(true, { tipo: 'modo_cambio', modo: 'panel' })).toBe(true)
  })

  it("pasar a 'notas' toma el foco para poder escribir", () => {
    expect(reducirFocoNotch(false, { tipo: 'modo_cambio', modo: 'notas' })).toBe(true)
  })

  it("pasar a 'guia' toma el foco para poder escribir la pregunta", () => {
    expect(reducirFocoNotch(false, { tipo: 'modo_cambio', modo: 'guia' })).toBe(true)
  })

  it('perder el foco no cierra la cajita de la guía', () => {
    expect(debeCerrarPanelAlPerderFoco('guia')).toBe(false)
  })

  it('perder el foco no cierra la captura de notas', () => {
    expect(debeCerrarPanelAlPerderFoco('notas')).toBe(false)
  })

  it('un aviso nuevo lo baja', () => {
    expect(
      reducirFocoNotch(true, {
        tipo: 'aviso_cambio',
        clave: '2:a',
        claveAnterior: '1:a',
      }),
    ).toBe(false)
    expect(
      reducirFocoNotch(true, {
        tipo: 'aviso_cambio',
        clave: '1:b',
        claveAnterior: '1:a',
      }),
    ).toBe(false)
    expect(
      reducirFocoNotch(true, {
        tipo: 'aviso_cambio',
        clave: '1:a',
        claveAnterior: '1:a',
      }),
    ).toBe(true)
  })

  it('tocar el aviso lo sube', () => {
    expect(reducirFocoNotch(false, { tipo: 'aviso_tocado' })).toBe(true)
  })

  it('abrir el panel pide foco; cerrarlo con toggle no', () => {
    expect(reducirFocoNotch(false, { tipo: 'alternar', eraPanel: false })).toBe(true)
    expect(reducirFocoNotch(true, { tipo: 'alternar', eraPanel: true })).toBe(false)
  })

  it('Esc cierra el foco', () => {
    expect(reducirFocoNotch(true, { tipo: 'esc' })).toBe(false)
  })
})

describe('debeCerrarPanelAlPerderFoco', () => {
  it("modo 'panel' cierra al perder foco", () => {
    expect(debeCerrarPanelAlPerderFoco('panel')).toBe(true)
  })

  it("modo 'aviso' y 'cerrado' no cierran", () => {
    expect(debeCerrarPanelAlPerderFoco('aviso')).toBe(false)
    expect(debeCerrarPanelAlPerderFoco('cerrado')).toBe(false)
  })
})

describe('claveAvisoNotch', () => {
  it('combina id y session_id', () => {
    expect(claveAvisoNotch({ id: 3, session_id: 's1', kind: 'asks', titulo: '', cuerpo: '' })).toBe('3:s1')
    expect(claveAvisoNotch(null)).toBe(null)
  })
})

describe('cerrarTrasBlur', () => {
  it('un blur pasajero (el foco volvió a la página) no cierra el panel', () => {
    expect(cerrarTrasBlur('panel', true)).toBe(false)
    expect(cerrarTrasBlur('reunion', true)).toBe(false)
  })
  it('si el foco se fue de verdad, cierra el panel y la reunión', () => {
    expect(cerrarTrasBlur('panel', false)).toBe(true)
    expect(cerrarTrasBlur('reunion', false)).toBe(true)
    expect(cerrarTrasBlur('guia', false)).toBe(false)
  })
  it('con la reunión en curso, la vista de la reunión queda abierta aunque mires otra ventana', () => {
    expect(cerrarTrasBlur('reunion', false, true)).toBe(false)
    expect(cerrarTrasBlur('panel', false, true)).toBe(true)
    expect(cerrarTrasBlur('reunion', false, false)).toBe(true)
  })
  it('espera un instante antes de decidir', () => {
    expect(GRACIA_BLUR_MS).toBeGreaterThanOrEqual(100)
    expect(GRACIA_BLUR_MS).toBeLessThanOrEqual(300)
  })
})
