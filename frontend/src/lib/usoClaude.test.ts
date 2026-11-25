import { describe, expect, it } from 'vitest'
import { detalleTokens, fmtUsd, itemsDesglose, limiteEstado, normalizeClaudeUso, pctLabel, reinicioLabel, usoHoyLine, type UsoFila } from './usoClaude'

const tk = (total: number) => ({ input: 1, cache_write: 2, cache_read: total - 4, output: 1, mensajes: 3, total })
const fila = (id: string, total: number, tipo: UsoFila['tipo'] = ''): UsoFila => ({ id, nombre: id.toUpperCase(), detalle: '', tipo, usd: null, usdParcial: false, ...tk(total) })

describe('normalizeClaudeUso', () => {
  it('rellena lo que falta y descarta basura', () => {
    const u = normalizeClaudeUso({
      totales: { hoy: { input: 5, total: 5 }, '7d': { total: -3 } },
      historial: [{ fecha: '2026-05-01', total: 10 }, { fecha: 'ayer', total: 1 }, null],
      desglose: { hoy: { sesiones: [{ id: 's1', nombre: 'Login', total: 9 }, { nombre: 'sin id' }], modelos: 'x' } },
      limites: { five_hour: { pct: 140, resets_at: '2026-05-01T10:00:00Z' }, seven_day: { pct: 'mucho' } },
    })
    expect(u.totales.hoy.total).toBe(5)
    expect(u.totales['7d'].total).toBe(0)
    expect(u.totales['30d']).toEqual({ input: 0, cache_write: 0, cache_read: 0, output: 0, mensajes: 0, total: 0, usd: null, usdParcial: false })
    expect(u.historial.map((d) => d.fecha)).toEqual(['2026-05-01'])
    expect(u.desglose.hoy.sesiones).toEqual([{ id: 's1', nombre: 'Login', detalle: '', tipo: '', usd: null, usdParcial: false, input: 0, cache_write: 0, cache_read: 0, output: 0, mensajes: 0, total: 9 }])
    expect(u.desglose.hoy.modelos).toEqual([])
    expect(u.desglose['30d'].proyectos).toEqual([])
    expect(u.limites?.fiveHour).toEqual({ pct: 100, resetsAt: '2026-05-01T10:00:00Z', vencido: false })
    expect(u.limites?.sevenDay).toBeNull()
  })

  it('conserva el usd y pone null si falta o no es un número válido', () => {
    const u = normalizeClaudeUso({
      totales: { hoy: { total: 5, usd: 4.1, usd_parcial: true }, '7d': { total: 5, usd: 'mucho' }, '30d': { total: 5, usd: -2 } },
      historial: [{ fecha: '2026-05-01', total: 10, usd: 1.5 }],
      desglose: { hoy: { sesiones: [{ id: 'a', total: 1, usd: 0 }, { id: 'b', total: 1, usd: null }, { id: 'c', total: 1 }] } },
    })
    expect(u.totales.hoy.usd).toBe(4.1)
    expect(u.totales.hoy.usdParcial).toBe(true)
    expect(u.totales['7d'].usd).toBeNull()
    expect(u.totales['30d'].usd).toBeNull()
    expect(u.historial[0].usd).toBe(1.5)
    expect(u.desglose.hoy.sesiones.map((f) => f.usd)).toEqual([0, null, null])
  })

  it('sin límites del plan no inventa nada', () => {
    expect(normalizeClaudeUso({ limites: null }).limites).toBeNull()
    expect(normalizeClaudeUso({ limites: { five_hour: {} } }).limites).toBeNull()
    expect(normalizeClaudeUso(undefined).historial).toEqual([])
  })
})

describe('itemsDesglose', () => {
  it('calcula porcentajes y deja a Otras con su color fijo', () => {
    const items = itemsDesglose([fila('a', 60), fila('b', 30), fila('_otras', 10, 'otras')])
    expect(items.map((i) => Math.round(i.pct))).toEqual([60, 30, 10])
    expect(items[2].color).toBe('var(--text-4)')
    expect(items[0].color).not.toBe(items[1].color)
    expect(items[0].label).toBe('A')
    expect(items[0].tokens.total).toBe(60)
  })
  it('con todo en cero no divide por cero', () => {
    expect(itemsDesglose([fila('a', 0)])[0].pct).toBe(0)
  })

  it('cuenta como otras la fila centinela o de tipo desconocido', () => {
    const u = normalizeClaudeUso({ desglose: { hoy: { sesiones: [{ id: 'a', total: 5 }, { id: 'centinela', tipo: 'centinela', total: 9 }, { id: 'x', tipo: 'futuro', total: 2 }] } } })
    expect(u.desglose.hoy.sesiones.map((f) => [f.id, f.tipo, f.total])).toEqual([['a', '', 5], ['centinela', 'otras', 9], ['x', 'otras', 2]])
  })
})

describe('reinicioLabel', () => {
  const now = new Date('2026-05-04T12:00:00')
  it('minutos, horas y fecha', () => {
    expect(reinicioLabel({ pct: 10, resetsAt: new Date('2026-05-04T12:25:00').toISOString(), vencido: false }, now)).toBe('se reinicia en 25 min')
    expect(reinicioLabel({ pct: 10, resetsAt: new Date('2026-05-04T14:10:00').toISOString(), vencido: false }, now)).toBe('se reinicia en 2 h 10 min')
    expect(reinicioLabel({ pct: 10, resetsAt: new Date('2026-05-04T15:00:00').toISOString(), vencido: false }, now)).toBe('se reinicia en 3 h')
    expect(reinicioLabel({ pct: 10, resetsAt: new Date('2026-05-07T09:05:00').toISOString(), vencido: false }, now)).toBe('se reinicia el jue 7 a las 09:05')
  })
  it('vencido o sin hora', () => {
    expect(reinicioLabel({ pct: 10, resetsAt: new Date('2026-05-04T11:00:00').toISOString(), vencido: false }, now)).toBe('ya se reinició')
    expect(reinicioLabel({ pct: 10, resetsAt: null, vencido: true }, now)).toBe('ya se reinició')
    expect(reinicioLabel({ pct: 10, resetsAt: null, vencido: false }, now)).toBe('sin hora de reinicio')
  })
})

describe('detalles', () => {
  it('detalleTokens suma la caché y pluraliza', () => {
    expect(detalleTokens({ input: 1200, cache_write: 500, cache_read: 1500, output: 30, mensajes: 1, total: 3230 })).toBe('1.2 k entrada · 2 k caché · 30 salida · 1 mensaje')
  })
  it('pctLabel y limiteEstado', () => {
    expect(pctLabel(0.4, 3)).toBe('<1')
    expect(pctLabel(0, 0)).toBe('0')
    expect(pctLabel(33.6, 3)).toBe('34')
    expect([limiteEstado(10), limiteEstado(80), limiteEstado(97)]).toEqual(['ok', 'aviso', 'tope'])
  })
})

describe('formato de dólares', () => {
  const usd = (n: number) => new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'USD' }).format(n)
  it('usa Intl en USD con coma decimal y deja guion si no hay precio', () => {
    expect(fmtUsd(4.1)).toBe(usd(4.1))
    expect(fmtUsd(4.1)).toContain('4,10')
    expect(fmtUsd(0)).toBe(usd(0))
    expect(fmtUsd(null)).toBe('—')
  })
  it('usoHoyLine: tokens y dólares de hoy, o solo tokens sin precio, o nada sin uso', () => {
    expect(usoHoyLine({ total: 312_000, usd: 4.1 })).toBe(`312 k tok · ≈ ${usd(4.1)} hoy`)
    expect(usoHoyLine({ total: 312_000, usd: null })).toBe('312 k tok · ≈ — hoy')
    expect(usoHoyLine({ total: 0, usd: 0 })).toBe('')
    expect(usoHoyLine(null)).toBe('')
    expect(usoHoyLine(undefined)).toBe('')
  })
})
