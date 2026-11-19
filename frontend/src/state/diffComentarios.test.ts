// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'

const base = { path: 'a.ts', lado: 'nuevo' as const, desde: 1, hasta: 2, fragmento: 'x', texto: 'hola' }

async function fresco() {
  vi.resetModules()
  const { ApiError } = await import('../api/types')
  return { ...(await import('./diffComentarios')), ApiError }
}

beforeEach(() => localStorage.clear())

describe('state/diffComentarios', () => {
  it('agrega, edita y quita por sesión', async () => {
    const s = await fresco()
    const c = s.agregar('s1', base)!
    s.agregar('s2', { ...base, texto: 'otra' })
    expect(s.pendientes('s1')).toHaveLength(1)
    s.editar('s1', c.id, 'cambiado')
    expect(s.pendientes('s1')[0].texto).toBe('cambiado')
    s.quitar('s1', c.id)
    expect(s.pendientes('s1')).toHaveLength(0)
    expect(s.pendientes('s2')).toHaveLength(1)
  })

  it('no pasa de 10 comentarios', async () => {
    const s = await fresco()
    for (let i = 0; i < 10; i++) expect(s.agregar('s1', base)).not.toBeNull()
    expect(s.agregar('s1', base)).toBeNull()
  })

  it('sobrevive a recargar (localStorage) y es por sesión', async () => {
    const s = await fresco()
    s.agregar('s1', base)
    const s2 = await fresco()
    expect(s2.pendientes('s1')).toHaveLength(1)
    expect(s2.pendientes('s2')).toHaveLength(0)
  })

  it('un storage que tira excepción no rompe', async () => {
    const get = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('no') })
    const set = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('no') })
    const s = await fresco()
    expect(s.agregar('s1', base)).not.toBeNull()
    expect(s.pendientes('s1')).toHaveLength(1)
    get.mockRestore()
    set.mockRestore()
  })

  it('mandar usa un id estable mientras la lista no cambie y vacía al tener éxito', async () => {
    const s = await fresco()
    const api = vi.fn().mockRejectedValueOnce(new s.ApiError(502, 'cayó')).mockResolvedValue({ ok: true, enviados: 1 })
    s.setComentariosApi(api)
    s.agregar('s1', base)
    expect(await s.mandar('s1')).toBe(false)
    expect(s.faseDe('s1')).toEqual({ fase: 'error', error: 'cayó' })
    expect(s.pendientes('s1')).toHaveLength(1)
    expect(await s.mandar('s1')).toBe(true)
    expect(api.mock.calls[0][1].id).toBe(api.mock.calls[1][1].id)
    expect(api.mock.calls[0][1].comentarios[0]).toEqual(base)
    expect(s.pendientes('s1')).toHaveLength(0)
    expect(s.faseDe('s1').fase).toBe('ok')
  })

  it('cambiar la lista después de un error genera otro id', async () => {
    const s = await fresco()
    const api = vi.fn().mockRejectedValueOnce(new s.ApiError(502, 'x')).mockResolvedValue({ ok: true, enviados: 2 })
    s.setComentariosApi(api)
    s.agregar('s1', base)
    await s.mandar('s1')
    s.agregar('s1', base)
    await s.mandar('s1')
    expect(api.mock.calls[0][1].id).not.toBe(api.mock.calls[1][1].id)
  })

  it('"Ya se mandó" (409) cuenta como éxito; otro 409 no', async () => {
    const s = await fresco()
    s.setComentariosApi(vi.fn().mockRejectedValue(new s.ApiError(409, 'Ya se mandó ese mensaje')))
    s.agregar('s1', base)
    expect(await s.mandar('s1')).toBe(true)
    expect(s.pendientes('s1')).toHaveLength(0)
    s.setComentariosApi(vi.fn().mockRejectedValue(new s.ApiError(409, 'Ese archivo ya no está entre los cambios: tocá Actualizar')))
    s.agregar('s1', base)
    expect(await s.mandar('s1')).toBe(false)
    expect(s.faseDe('s1').error).toContain('Actualizar')
    expect(s.pendientes('s1')).toHaveLength(1)
  })

  it('al terminar bien quita solo lo que se mandó, no lo agregado mientras tanto', async () => {
    const s = await fresco()
    let fin!: () => void
    s.setComentariosApi(vi.fn(() => new Promise<{ ok: boolean; enviados: number }>((r) => { fin = () => r({ ok: true, enviados: 1 }) })))
    s.agregar('s1', base)
    const a = s.mandar('s1')
    s.agregar('s1', { ...base, texto: 'llegó después' })
    fin()
    expect(await a).toBe(true)
    expect(s.pendientes('s1').map((c) => c.texto)).toEqual(['llegó después'])
    expect(s.faseDe('s1').fase).toBe('ok')
  })

  it('el id de operación sobrevive a recargar: el reenvío usa el mismo id', async () => {
    const s = await fresco()
    const api = vi.fn().mockRejectedValue(new s.ApiError(502, 'cayó'))
    s.setComentariosApi(api)
    s.agregar('s1', base)
    await s.mandar('s1')
    const s2 = await fresco()
    const api2 = vi.fn().mockResolvedValue({ ok: true, enviados: 1 })
    s2.setComentariosApi(api2)
    expect(await s2.mandar('s1')).toBe(true)
    expect(api2.mock.calls[0][1].id).toBe(api.mock.calls[0][1].id)
  })

  it('editar o agregar después de un error descarta el id persistido', async () => {
    const s = await fresco()
    const api = vi.fn().mockRejectedValue(new s.ApiError(502, 'x'))
    s.setComentariosApi(api)
    s.agregar('s1', base)
    await s.mandar('s1')
    s.agregar('s1', base)
    const s2 = await fresco()
    const api2 = vi.fn().mockResolvedValue({ ok: true, enviados: 2 })
    s2.setComentariosApi(api2)
    await s2.mandar('s1')
    expect(api2.mock.calls[0][1].id).not.toBe(api.mock.calls[0][1].id)
  })

  it('agregar durante un envío en vuelo no rehabilita ni permite un segundo envío', async () => {
    const s = await fresco()
    let fin!: () => void
    const api = vi.fn(() => new Promise<{ ok: boolean; enviados: number }>((r) => { fin = () => r({ ok: true, enviados: 1 }) }))
    s.setComentariosApi(api)
    s.agregar('s1', base)
    const a = s.mandar('s1')
    s.agregar('s1', { ...base, texto: 'a destiempo' })
    s.editar('s1', s.pendientes('s1')[1].id, 'editado')
    expect(s.faseDe('s1').fase).toBe('enviando')
    expect(await s.mandar('s1')).toBe(false)
    expect(api).toHaveBeenCalledTimes(1)
    fin()
    expect(await a).toBe(true)
    expect(s.pendientes('s1').map((c) => c.texto)).toEqual(['editado'])
    expect(JSON.parse(localStorage.getItem('orq.comentariosDiff')!).ops).toEqual({})
  })

  it('un doble toque no manda dos veces', async () => {
    const s = await fresco()
    let fin!: () => void
    const api = vi.fn(() => new Promise<{ ok: boolean; enviados: number }>((r) => { fin = () => r({ ok: true, enviados: 1 }) }))
    s.setComentariosApi(api)
    s.agregar('s1', base)
    const a = s.mandar('s1')
    expect(await s.mandar('s1')).toBe(false)
    fin()
    expect(await a).toBe(true)
    expect(api).toHaveBeenCalledTimes(1)
  })
})
