import { afterEach, describe, expect, it, vi } from 'vitest'
import { listarMudanza, mudar, mudarTodas, normalizeMudanzaListado, retomarMudanza } from './mudanzaApi'

const ID_RE = /^[A-Za-z0-9_-]{8,64}$/

describe('normalizeMudanzaListado', () => {
  it('arrays faltantes → []', () => {
    expect(normalizeMudanzaListado({ disponible: true })).toEqual({
      disponible: true,
      motivo: '',
      sesiones: [],
      pendientes: [],
    })
  })

  it('normaliza candidatas y pendientes', () => {
    const l = normalizeMudanzaListado({
      disponible: true,
      motivo: 'ok',
      sesiones: [{ pane_id: 'p1', session_id: 's', nombre: 'A', workspace: 'w', puede: true, motivo: '' }],
      pendientes: [{ id: 'm1', pane_viejo: 'p0', session_id: 's', nombre: 'B', workspace: 'w', estado: 'pendiente' }],
    })
    expect(l.sesiones).toHaveLength(1)
    expect(l.pendientes[0].id).toBe('m1')
  })
})

describe('mudanzaApi POST', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('cada POST manda confirmado: true y un id válido', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true, mudanza: {}, mudadas: [], saltadas: [], fallidas: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)

    await mudar('pane-1')
    await mudarTodas(['a', 'b'])
    await retomarMudanza('mud-xyz-12345678')

    const bodies = fetch.mock.calls.map((c) => {
      const init = (c as unknown as [string, RequestInit])[1]
      return JSON.parse(init.body as string)
    })
    expect(bodies).toHaveLength(3)
    for (const b of bodies) {
      expect(b.confirmado).toBe(true)
      expect(b.id).toMatch(ID_RE)
    }
    expect(bodies[0]).toMatchObject({ pane_id: 'pane-1' })
    expect(bodies[1]).toMatchObject({ pane_ids: ['a', 'b'] })
    expect(bodies[2]).toMatchObject({ mudanza_id: 'mud-xyz-12345678' })
  })

  it('GET listar normaliza la respuesta', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ disponible: false, motivo: 'off' }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    const l = await listarMudanza()
    expect(l).toEqual({ disponible: false, motivo: 'off', sesiones: [], pendientes: [] })
    expect((fetch.mock.calls[0] as unknown as [string])[0]).toBe('/api/mudanza')
  })
})
