import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from './types'
import { createHttpApi } from './http'

const respuesta = (status: number, body: unknown) => ({
  ok: status < 400,
  status,
  statusText: '',
  headers: new Headers(),
  clone() {
    return this
  },
  async json() {
    return body
  },
})

describe('setSilencio', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('hace PUT al sid con el valor', async () => {
    const f = vi.fn().mockResolvedValue(respuesta(200, { ok: true }))
    vi.stubGlobal('fetch', f)
    await createHttpApi(vi.fn()).setSilencio('abc 1', true)
    expect(f).toHaveBeenCalledWith(
      '/api/sesiones/abc%201/silencio',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify({ on: true }) }),
    )
  })

  it('un 401 llega a onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(401, { detail: 'no' })))
    await expect(createHttpApi(onUnauthorized).setSilencio('a', false)).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})
