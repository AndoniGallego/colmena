import { describe, expect, it, vi } from 'vitest'
import { ApiError, type Api } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }), addEventListener() {} })
})
import { init, stopErr, stopOk, stopSession, stopping } from './app'

describe('stopSession', () => {
  it('frena, avisa y no deja doble disparo mientras está en curso', async () => {
    let release: () => void = () => {}
    const fn = vi.fn().mockReturnValue(new Promise<void>((r) => (release = r)))
    init({ stopSession: fn } as unknown as Api)
    const first = stopSession('wG:p1')
    expect(stopping['wG:p1']).toBe(true)
    expect(await stopSession('wG:p1')).toBe(false)
    release()
    expect(await first).toBe(true)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(stopOk['wG:p1']).toBe(true)
    expect(stopping['wG:p1']).toBeUndefined()
  })

  it('un error muestra el detalle', async () => {
    init({ stopSession: vi.fn().mockRejectedValue(new ApiError(409, 'La sesión no está trabajando')) } as unknown as Api)
    expect(await stopSession('wG:p1')).toBe(false)
    expect(stopErr['wG:p1']).toBe('La sesión no está trabajando')
  })
})
