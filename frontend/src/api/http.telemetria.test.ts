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

describe('telemetriaComandoNo', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('hace POST con la clave', async () => {
    const f = vi.fn().mockResolvedValue(respuesta(200, { ok: true }))
    vi.stubGlobal('fetch', f)
    await createHttpApi(vi.fn()).telemetriaComandoNo('0123456789abcdef')
    expect(f).toHaveBeenCalledWith(
      '/api/telemetria/comando-no',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ clave: '0123456789abcdef' }) }),
    )
  })

  it('un 401 rechaza pero no llama a onUnauthorized (la telemetría no desloguea)', async () => {
    const onUnauthorized = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(401, { detail: 'no' })))
    await expect(createHttpApi(onUnauthorized).telemetriaComandoNo('0123456789abcdef')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).not.toHaveBeenCalled()
  })
})

describe('marcarPropuesta', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('hace POST con la decisión y devuelve id y estado', async () => {
    const f = vi.fn().mockResolvedValue(respuesta(200, { id: 'aaaaaaaaaaaa', estado: 'ignorada', silenciada_hasta: 'x' }))
    vi.stubGlobal('fetch', f)
    const r = await createHttpApi(vi.fn()).marcarPropuesta('aaaaaaaaaaaa', 'ignorar')
    expect(f).toHaveBeenCalledWith(
      '/api/telemetria/propuestas/aaaaaaaaaaaa',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ decision: 'ignorar' }) }),
    )
    expect(r).toEqual({ id: 'aaaaaaaaaaaa', estado: 'ignorada' })
  })

  it('es una acción del usuario: un 401 llama a onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(401, { detail: 'no' })))
    await expect(createHttpApi(onUnauthorized).marcarPropuesta('aaaaaaaaaaaa', 'hacer')).rejects.toBeInstanceOf(ApiError)
    expect(onUnauthorized).toHaveBeenCalled()
  })
})
