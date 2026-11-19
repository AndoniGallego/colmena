import { describe, expect, it } from 'vitest'
import { barras, desglose, diaLabel, fmtTokens } from './tokens'

describe('fmtTokens', () => {
  it('abrevia en k y M', () => {
    expect(fmtTokens(950)).toBe('950')
    expect(fmtTokens(1500)).toBe('1.5 k')
    expect(fmtTokens(640_000)).toBe('640 k')
    expect(fmtTokens(1_500_000)).toBe('1.5 M')
    expect(fmtTokens(2_000_000)).toBe('2 M')
  })
})

describe('desglose', () => {
  it('reparte en porcentajes que suman 100', () => {
    const t = desglose({ input: 20, cache_write: 180, cache_read: 700, output: 100 })
    expect(t.map((x) => x.pct)).toEqual([2, 18, 70, 10])
    expect(t.reduce((s, x) => s + x.pct, 0)).toBe(100)
  })
  it('sin uso no divide por cero', () => {
    expect(desglose({ input: 0, cache_write: 0, cache_read: 0, output: 0 }).every((x) => x.pct === 0)).toBe(true)
  })
})

describe('barras', () => {
  const dia = (fecha: string, total: number) => ({ fecha, input: 0, cache_write: 0, cache_read: 0, output: 0, mensajes: 0, total })
  const dias = [dia('2026-10-26', 0), dia('2026-10-27', 500_000), dia('2026-10-28', 1_000_000), dia('2026-10-29', 2_000_000)]

  it('toma los últimos n y escala contra el máximo', () => {
    const r = barras(dias, 2, 0)
    expect(r.barras.map((b) => b.fecha)).toEqual(['2026-10-28', '2026-10-29'])
    expect(r.barras[1].h).toBe(1)
    expect(r.barras[0].h).toBe(0.5)
    expect(r.topeH).toBeNull()
  })
  it('el tope entra en la escala y marca los días que lo pasaron', () => {
    const r = barras(dias, 4, 1_000_000)
    expect(r.topeH).toBe(0.5)
    expect(r.barras.map((b) => b.tope)).toEqual([false, false, true, true])
  })
  it('un tope mayor al máximo achica las barras', () => {
    expect(barras(dias, 4, 4_000_000).barras[3].h).toBe(0.5)
  })
  it('etiqueta el día de la semana', () => {
    expect(diaLabel('2026-10-29')).toBe('jue 29')
    expect(diaLabel('x')).toBe('x')
  })
})
