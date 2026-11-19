import { describe, expect, it } from 'vitest'
import { fechaLarga, hoyLocal, shiftFecha } from './fechas'

describe('fechas', () => {
  it('formatea y mueve el día', () => {
    expect(fechaLarga('2026-11-01')).toBe('Domingo 1 de noviembre')
    expect(fechaLarga('2026-10-31')).toBe('Sábado 31 de octubre')
    expect(shiftFecha('2026-11-01', -1)).toBe('2026-10-31')
    expect(shiftFecha('2026-03-01', -1)).toBe('2026-02-28')
    expect(hoyLocal(new Date(2026, 10, 1, 23, 59).getTime())).toBe('2026-11-01')
  })
})
