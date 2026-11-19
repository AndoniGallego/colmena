import { describe, expect, it } from 'vitest'
import {
  estadoTarjeta,
  indiceUltimaPorSig,
  limpiarFilaNovedad,
  recomendadaLabel,
  toPreguntaRef,
} from './preguntaCard'

describe('toPreguntaRef', () => {
  it('acepta sig y campos opcionales', () => {
    expect(toPreguntaRef({ sig: 'abc', recomendada: 'Sí', porque: 'Es lo más seguro' })).toEqual({
      sig: 'abc',
      recomendada: 'Sí',
      porque: 'Es lo más seguro',
    })
    expect(toPreguntaRef({ sig: 'x' })).toEqual({ sig: 'x' })
  })

  it('sin sig válido devuelve null', () => {
    expect(toPreguntaRef(null)).toBeNull()
    expect(toPreguntaRef({})).toBeNull()
    expect(toPreguntaRef({ sig: '  ' })).toBeNull()
  })
})

describe('indiceUltimaPorSig', () => {
  it('marca el último mensaje que trae cada sig', () => {
    const m = indiceUltimaPorSig([
      { idx: 1, sigs: ['a'] },
      { idx: 2, sigs: ['a', 'b'] },
      { idx: 3, sigs: ['b'] },
    ])
    expect(m.get('a')).toBe(2)
    expect(m.get('b')).toBe(3)
  })
})

describe('estadoTarjeta', () => {
  it('activa solo si hay lote, es la última y no está contestada', () => {
    expect(estadoTarjeta({ hayLote: true, esUltima: true, contestada: null })).toBe('activa')
    expect(estadoTarjeta({ hayLote: true, esUltima: false, contestada: null })).toBe('obsoleta')
    expect(estadoTarjeta({ hayLote: false, esUltima: true, contestada: null })).toBe('sin_lote')
    expect(estadoTarjeta({ hayLote: false, esUltima: true, contestada: 'Sí' })).toBe('contestada')
    expect(estadoTarjeta({ hayLote: true, esUltima: true, contestada: 'No' })).toBe('contestada')
  })
})

describe('recomendadaLabel', () => {
  const lote = {
    preguntas: [{ pregunta: '¿Va?', opciones: [{ label: 'A', detalle: '', recomendada: true }, { label: 'B', detalle: '', recomendada: false }] }],
  }
  it('prioriza la del bloque', () => {
    expect(recomendadaLabel({ sig: 's', recomendada: 'B' }, lote)).toBe('B')
  })
  it('cae al lote si el bloque no trae', () => {
    expect(recomendadaLabel({ sig: 's' }, lote)).toBe('A')
  })
})

describe('limpiarFilaNovedad', () => {
  it('saca sig, pedido_id e ids crudos de pane', () => {
    const raw = 'Login (w1:p2) pregunta: «¿listo?» (sig=abc123)'
    expect(limpiarFilaNovedad(raw)).toBe('Login pregunta: «¿listo?»')
    const perm = 'PS9 · Back (g26:p28) espera permiso: «make test» (pedido_id=pid-1, gris: dudoso)'
    expect(limpiarFilaNovedad(perm)).toBe('PS9 · Back espera permiso: «make test»')
  })
})
