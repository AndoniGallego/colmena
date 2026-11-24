import { describe, expect, it } from 'vitest'
import { fechaReunion, MOTIVO_LABEL, toReunion } from './reunion'

const base = {
  titulo: 'Daily', inicio: 1_795_000_000.5, fin: 1_795_000_900, duracion_s: 900, repos: ['a', 'b'],
  motivo: 'terminada', resumen: ['uno'], pendientes: ['dos'],
  tocadas: [{ texto: 'Pago', tipo: 'pregunta', respuesta: 'Sí', archivos: ['x.py'] }],
}

describe('toReunion', () => {
  it('lee una reunión válida', () => {
    const r = toReunion(base)!
    expect(r).toMatchObject({ titulo: 'Daily', duracion_s: 900, repos: ['a', 'b'], motivo: 'terminada', resumen: ['uno'], pendientes: ['dos'] })
    expect(r.tocadas).toEqual([{ texto: 'Pago', tipo: 'pregunta', respuesta: 'Sí', archivos: ['x.py'] }])
    expect(r.inicio).not.toBe('—')
  })
  it('devuelve null con lo que no es un objeto o con JSON roto', () => {
    for (const v of [null, undefined, 'x', 3, [], '{no es json']) expect(toReunion(v)).toBeNull()
  })
  it('acepta el JSON como texto', () => {
    expect(toReunion(JSON.stringify(base))?.titulo).toBe('Daily')
  })
  it('valida tipos: fechas que no son número dan "—" y el motivo raro cae a interrumpida', () => {
    const r = toReunion({ ...base, inicio: 'ayer', fin: null, duracion_s: 'x', motivo: 'rara' })!
    expect(r.inicio).toBe('—')
    expect(r.fin).toBe('—')
    expect(r.duracion_s).toBe(0)
    expect(r.motivo).toBe('interrumpida')
  })
  it('recorta listas y textos, y descarta ítems inválidos', () => {
    const r = toReunion({
      ...base,
      repos: Array.from({ length: 50 }, (_, i) => `r${i}`),
      resumen: [...Array.from({ length: 80 }, (_, i) => `p${i}`), 3, ''],
      pendientes: ['x'.repeat(2000)],
      tocadas: [...Array.from({ length: 80 }, () => ({ texto: 't', tipo: 'a', respuesta: 'r', archivos: [] })), 'no', { texto: 5 }],
    })!
    expect(r.repos.length).toBe(20)
    expect(r.resumen.length).toBe(40)
    expect(r.pendientes[0].length).toBeLessThanOrEqual(501)
    expect(r.tocadas.length).toBe(40)
  })
  it('sin título usa un título por defecto', () => {
    expect(toReunion({ ...base, titulo: 4 })?.titulo).toBe('Reunión')
  })
})

describe('fechaReunion y motivos', () => {
  it('formatea epoch en segundos y tolera lo que no es número', () => {
    expect(fechaReunion(1_795_000_000)).toMatch(/\d/)
    expect(fechaReunion(NaN)).toBe('—')
    expect(fechaReunion('1')).toBe('—')
    expect(fechaReunion(undefined)).toBe('—')
  })
  it('cada motivo tiene etiqueta', () => {
    expect(Object.keys(MOTIVO_LABEL).sort()).toEqual(['interrumpida', 'llena', 'sin_pc', 'terminada'])
  })
})
