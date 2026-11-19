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

describe('irAPc', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('hace POST al sid', async () => {
    const f = vi.fn().mockResolvedValue(respuesta(200, { ok: true }))
    vi.stubGlobal('fetch', f)
    await createHttpApi(vi.fn()).irAPc('abc 1')
    expect(f).toHaveBeenCalledWith('/api/sesiones/abc%201/ir-a-pc', expect.objectContaining({ method: 'POST' }))
  })

  it('un 409 trae el mensaje del backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(409, { detail: 'Esta sesión no corre en una terminal de Colmena' })))
    await expect(createHttpApi(vi.fn()).irAPc('a')).rejects.toMatchObject({ status: 409, detail: 'Esta sesión no corre en una terminal de Colmena' })
  })

  it('un 401 llega a onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(401, { detail: 'no' })))
    await expect(createHttpApi(onUnauthorized).irAPc('a')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})
