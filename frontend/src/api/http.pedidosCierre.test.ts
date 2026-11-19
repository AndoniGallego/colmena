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

describe('abrirPedidoPestana con opciones', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('manda huella y forzar como cuerpo JSON', async () => {
    const f = vi.fn().mockResolvedValue(respuesta(200, { ok: true, pane_id: '', cerrada: true }))
    vi.stubGlobal('fetch', f)
    const r = await createHttpApi(vi.fn()).abrirPedidoPestana('id', { forzar: true, huella: 'h' })
    expect(f).toHaveBeenCalledWith(
      '/api/pedidos-pestana/id/abrir',
      expect.objectContaining({ method: 'POST', body: '{"forzar":true,"huella":"h"}' }),
    )
    expect(r.cerrada).toBe(true)
  })

  it('sin opciones no manda cuerpo', async () => {
    const f = vi.fn().mockResolvedValue(respuesta(200, { ok: true, pane_id: 'w1:p2' }))
    vi.stubGlobal('fetch', f)
    await createHttpApi(vi.fn()).abrirPedidoPestana('id')
    expect(f.mock.calls[0][1].body).toBeUndefined()
  })

  it('guardando resuelve con pane_id vacío', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(200, { ok: true, pane_id: '', guardando: true })))
    const r = await createHttpApi(vi.fn()).abrirPedidoPestana('id')
    expect(r.guardando).toBe(true)
    expect(r.pane_id).toBe('')
  })

  it('sin cerrada ni guardando y sin pane_id rechaza', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(200, { ok: true, pane_id: '' })))
    await expect(createHttpApi(vi.fn()).abrirPedidoPestana('id')).rejects.toBeInstanceOf(ApiError)
  })
})

describe('vistaCierrePedido', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('hace POST a vista-cierre y normaliza', async () => {
    const f = vi.fn().mockResolvedValue(respuesta(200, { trabajando: true, estados: ['working'], huella: 'h' }))
    vi.stubGlobal('fetch', f)
    const r = await createHttpApi(vi.fn()).vistaCierrePedido('id')
    expect(f).toHaveBeenCalledWith('/api/pedidos-pestana/id/vista-cierre', expect.objectContaining({ method: 'POST' }))
    expect(r).toEqual({ trabajando: true, estados: ['working'], huella: 'h' })
  })

  it('una respuesta inválida rechaza con ApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(respuesta(200, { trabajando: true })))
    await expect(createHttpApi(vi.fn()).vistaCierrePedido('id')).rejects.toBeInstanceOf(ApiError)
  })
})
