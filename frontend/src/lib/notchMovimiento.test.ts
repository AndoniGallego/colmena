import { describe, expect, it } from 'vitest'
import {
  ANCHO_NOTAS,
  anchoPara,
  anchoVentanaFijo,
  cuerpoVisible,
  pillAbierto,
  superaUmbral,
  tamanoAlCambiarFoco,
  UMBRAL_ARRASTRE,
} from './notchMovimiento'

describe('tamanoAlCambiarFoco', () => {
  it('con tamaño previo repite ancho/alto con el foco nuevo', () => {
    expect(tamanoAlCambiarFoco({ ancho: 472, alto: 120 }, true)).toEqual({
      ancho: 472,
      alto: 120,
      foco: true,
    })
    expect(tamanoAlCambiarFoco({ ancho: 472, alto: 120 }, false)).toEqual({
      ancho: 472,
      alto: 120,
      foco: false,
    })
  })

  it('sin tamaño previo no pide nada', () => {
    expect(tamanoAlCambiarFoco(null, true)).toBeNull()
    expect(tamanoAlCambiarFoco(null, false)).toBeNull()
  })
})

describe('anchoVentanaFijo', () => {
  it('en pantalla grande usa el máximo entre panel y aviso (440)', () => {
    expect(anchoVentanaFijo(1920)).toBe(440)
  })

  it('en pantalla chica usa pantalla menos 24', () => {
    expect(anchoVentanaFijo(400)).toBe(376)
  })

  it('coincide con Math.max de anchoPara panel y aviso', () => {
    const p = 800
    expect(anchoVentanaFijo(p)).toBe(Math.max(anchoPara('panel', 0, p), anchoPara('aviso', 0, p)))
  })
})

describe('notchMovimiento arrastre', () => {
  it('el umbral es 5 px', () => {
    expect(UMBRAL_ARRASTRE).toBe(5)
  })

  it('superaUmbral usa la hipotenusa', () => {
    expect(superaUmbral(5, 0)).toBe(false)
    expect(superaUmbral(4, 4)).toBe(true)
    expect(superaUmbral(0, 6)).toBe(true)
  })
})

describe('notchMovimiento visibilidad al cerrar', () => {
  it('cuerpo oculto en cerrado salvo animación de cierre', () => {
    expect(cuerpoVisible('cerrado', false)).toBe(false)
    expect(cuerpoVisible('cerrado', true)).toBe(true)
    expect(cuerpoVisible('panel', false)).toBe(true)
    expect(cuerpoVisible('aviso', false)).toBe(true)
  })

  it('pill abierto coincide con cuerpo durante el cierre', () => {
    expect(pillAbierto('cerrado', false)).toBe(false)
    expect(pillAbierto('cerrado', true)).toBe(true)
    expect(pillAbierto('panel', false)).toBe(true)
    expect(pillAbierto('aviso', true)).toBe(true)
  })
})

describe('modo notas', () => {
  it('abre al ancho de la lista de notas y respeta pantallas chicas', () => {
    expect(ANCHO_NOTAS).toBe(420)
    expect(anchoPara('notas', 120, 1920)).toBe(ANCHO_NOTAS)
    expect(anchoPara('notas', 120, 300)).toBe(276)
  })

  it('muestra el cuerpo y la pastilla abierta', () => {
    expect(cuerpoVisible('notas', false)).toBe(true)
    expect(pillAbierto('notas', false)).toBe(true)
  })

  it('la ventana fija alcanza también para notas', () => {
    expect(anchoVentanaFijo(1920)).toBeGreaterThanOrEqual(anchoPara('notas', 0, 1920))
  })
})
