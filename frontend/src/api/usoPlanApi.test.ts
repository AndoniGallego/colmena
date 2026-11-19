import { describe, expect, it } from 'vitest'
import { getUsoLimites, normalizarUsoPlan } from './usoPlanApi'

const ok = (body: unknown, status = 200) => (async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch

describe('normalizarUsoPlan', () => {
  it('sin datos devuelve null', () => {
    expect(normalizarUsoPlan({ sin_datos: true })).toBeNull()
    expect(normalizarUsoPlan(null)).toBeNull()
    expect(normalizarUsoPlan({})).toBeNull()
  })
  it('normaliza ventanas y edad', () => {
    const p = normalizarUsoPlan({
      five_hour: { pct: 23.5, resets_at: '2026-11-17T15:00:00+00:00', vencido: false },
      seven_day: { pct: 140, resets_at: null, vencido: true },
      actualizado: '2026-11-17T12:00:00+00:00',
      edad_s: 90,
    })
    expect(p?.fiveHour?.pct).toBe(23.5)
    expect(p?.sevenDay).toEqual({ pct: 100, resetsAt: null, vencido: true })
    expect(p?.edadS).toBe(90)
    expect(p?.actualizado).toBe('2026-11-17T12:00:00+00:00')
  })
  it('descarta ventanas inválidas', () => {
    expect(normalizarUsoPlan({ five_hour: { pct: 'x' }, seven_day: { pct: 5 } })?.fiveHour).toBeNull()
  })
})

describe('getUsoLimites', () => {
  it('pide el endpoint liviano y normaliza', async () => {
    let url = ''
    const f = (async (u: string) => ((url = u), new Response(JSON.stringify({ five_hour: { pct: 1 }, edad_s: 3 })))) as unknown as typeof fetch
    expect((await getUsoLimites(f))?.fiveHour?.pct).toBe(1)
    expect(url).toBe('/api/uso/limites')
  })
  it('sin_datos da null', async () => {
    expect(await getUsoLimites(ok({ sin_datos: true }))).toBeNull()
  })
  it('error HTTP o de red lanza ApiError', async () => {
    await expect(getUsoLimites(ok({}, 401))).rejects.toMatchObject({ status: 401 })
    await expect(getUsoLimites((async () => { throw new Error('x') }) as unknown as typeof fetch)).rejects.toMatchObject({ status: 0 })
  })
})
