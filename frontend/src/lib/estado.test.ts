import { describe, expect, it } from 'vitest'
import { lineasEstado, toEstado } from './estado'
import { parseSegments } from './segments'
import { plainPreview, sinBloques } from './preview'

const bloque = (cuerpo: string) => '```estado\n' + cuerpo + '\n```'

describe('toEstado', () => {
  it('acepta los tres campos y recorta a 120 por palabra', () => {
    expect(toEstado({ hizo: 'Saqué el mapa', falta: 'Elegir', pide: '¿Cuál?', otro: 1 })).toEqual({ hizo: 'Saqué el mapa', falta: 'Elegir', pide: '¿Cuál?' })
    const largo = toEstado({ hizo: 'palabra '.repeat(30) })!.hizo!
    expect(largo.length).toBeLessThanOrEqual(121)
    expect(largo.endsWith('…')).toBe(true)
  })

  it('rechaza lo que no es objeto o no trae ningún texto', () => {
    expect(toEstado(null)).toBeNull()
    expect(toEstado([1])).toBeNull()
    expect(toEstado('x')).toBeNull()
    expect(toEstado({ hizo: 3, falta: '  ' })).toBeNull()
  })
})

describe('lineasEstado', () => {
  it('arma las líneas en orden con su marca', () => {
    expect(lineasEstado({ hizo: 'A', falta: 'B', pide: 'C' })).toEqual([
      { clave: 'hizo', marca: '✓', texto: 'A' },
      { clave: 'falta', marca: '…', texto: 'Falta: B' },
      { clave: 'pide', marca: '?', texto: 'C' },
    ])
    expect(lineasEstado({ falta: 'B' }).map((l) => l.clave)).toEqual(['falta'])
  })
})

describe('bloque estado en el chat', () => {
  it('se vuelve un segmento estado entre el texto', () => {
    const segs = parseSegments(`Listo.\n\n${bloque('{"hizo": "x", "pide": "¿Seguimos?"}')}`)
    expect(segs.map((s) => s.type)).toEqual(['md', 'estado'])
    expect(segs[1]).toEqual({ type: 'estado', data: { hizo: 'x', pide: '¿Seguimos?' } })
  })

  it('con JSON inválido queda como código', () => {
    const segs = parseSegments(bloque('{no es json'))
    expect(segs.map((s) => s.type)).toEqual(['md'])
  })

  it('mientras llega, muestra pendiente', () => {
    const segs = parseSegments('Va\n```estado\n{"hiz', true)
    expect(segs.map((s) => s.type)).toEqual(['md', 'pending'])
  })

  it('las vistas previas no muestran el bloque', () => {
    expect(sinBloques(`Listo.\n${bloque('{"hizo": "x"}')}`).trim()).toBe('Listo.')
    expect(plainPreview(`Listo.\n\n${bloque('{"hizo": "x"}')}`)).toBe('Listo.')
  })
})
