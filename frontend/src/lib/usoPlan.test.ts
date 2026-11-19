import { describe, expect, it } from 'vitest'
import { ariaPlan, faltaPara, nivel, textoCorto, viejo, ventanas, type UsoPlan } from './usoPlan'

const AHORA = Date.parse('2026-11-17T12:00:00Z')
const iso = (offsetMin: number) => new Date(AHORA + offsetMin * 60_000).toISOString()
const plan = (extra: Partial<UsoPlan> = {}): UsoPlan => ({
  fiveHour: { pct: 23.4, resetsAt: iso(130), vencido: false },
  sevenDay: { pct: 41, resetsAt: iso(3 * 24 * 60 + 4 * 60), vencido: false },
  actualizado: iso(-2),
  edadS: 120,
  ...extra,
})

describe('nivel', () => {
  it('corta en 70 y 90', () => {
    expect(nivel(0)).toBe('ok')
    expect(nivel(69.9)).toBe('ok')
    expect(nivel(70)).toBe('atento')
    expect(nivel(89.9)).toBe('atento')
    expect(nivel(90)).toBe('alto')
    expect(nivel(100)).toBe('alto')
  })
})

describe('faltaPara', () => {
  it('horas y minutos', () => expect(faltaPara(iso(130), AHORA)).toBe('2 h 10 min'))
  it('hora justa sin minutos', () => expect(faltaPara(iso(120), AHORA)).toBe('2 h'))
  it('solo minutos', () => expect(faltaPara(iso(45), AHORA)).toBe('45 min'))
  it('días y horas', () => expect(faltaPara(iso(3 * 24 * 60 + 4 * 60), AHORA)).toBe('3 d 4 h'))
  it('días justos', () => expect(faltaPara(iso(2 * 24 * 60), AHORA)).toBe('2 d'))
  it('menos de un minuto', () => expect(faltaPara(iso(0.2), AHORA)).toBe('menos de 1 min'))
  it('vencido o inválido', () => {
    expect(faltaPara(iso(-5), AHORA)).toBe('')
    expect(faltaPara(null, AHORA)).toBe('')
    expect(faltaPara('basura', AHORA)).toBe('')
  })
})

describe('textoCorto', () => {
  it('ambas ventanas redondeadas', () => expect(textoCorto(plan())).toBe('5h 23% · sem 41%'))
  it('una sola ventana', () => expect(textoCorto(plan({ sevenDay: null }))).toBe('5h 23%'))
  it('vencida muestra renovado', () => {
    expect(textoCorto(plan({ fiveHour: { pct: 90, resetsAt: iso(-1), vencido: true } }))).toBe('5h renovado · sem 41%')
  })
})

describe('viejo', () => {
  it('más de 30 minutos sin actualizar', () => {
    expect(viejo(plan({ actualizado: iso(-31) }), AHORA)).toBe(true)
    expect(viejo(plan({ actualizado: iso(-29) }), AHORA)).toBe(false)
  })
  it('sin fecha usa edadS', () => {
    expect(viejo(plan({ actualizado: null, edadS: 1801 }), AHORA)).toBe(true)
    expect(viejo(plan({ actualizado: null, edadS: 60 }), AHORA)).toBe(false)
  })
})

describe('ventanas y aria', () => {
  it('lista las ventanas presentes con su título', () => {
    expect(ventanas(plan()).map((v) => v.key)).toEqual(['5h', '7d'])
    expect(ventanas(plan({ fiveHour: null })).map((v) => v.key)).toEqual(['7d'])
  })
  it('aria describe ambas', () => {
    expect(ariaPlan(plan())).toBe('Plan de Claude: 23% de 5 horas, 41% semanal')
  })
})
