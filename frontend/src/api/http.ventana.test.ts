import { afterEach, describe, expect, it, vi } from 'vitest'
import { PIN_WRONG } from '../lib/dialogo'
import { createHttpApi } from './http'

describe('abrirVentana', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('PIN incorrecto no dispara onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
        clone() {
          return this
        },
        async json() {
          return { detail: PIN_WRONG }
        },
      }),
    )
    const api = createHttpApi(onUnauthorized)
    await expect(api.abrirVentana('000000')).rejects.toMatchObject({ status: 401, detail: PIN_WRONG })
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('401 de sesión vencida sí dispara onUnauthorized', async () => {
    const onUnauthorized = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        headers: new Headers(),
        clone() {
          return this
        },
        async json() {
          return { detail: 'sesión inválida' }
        },
      }),
    )
    const api = createHttpApi(onUnauthorized)
    await expect(api.abrirVentana('123456')).rejects.toMatchObject({ status: 401 })
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })
})
