import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => vi.unstubAllGlobals())

describe('httpPushApi', () => {
  it('un 400 con detail lanza ApiError cuyo message es el detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ detail: 'No hay dispositivos suscriptos' }),
      }),
    )
    vi.resetModules()
    const { httpPushApi } = await import('./pushApi')
    const { ApiError } = await import('./types')
    try {
      await httpPushApi.probarAviso('asks', 'celu')
      expect.unreachable('debía fallar')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as InstanceType<typeof ApiError>).message).toBe('No hay dispositivos suscriptos')
    }
  })
})
