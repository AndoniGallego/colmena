import { nextTick } from 'vue'
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { normalizeAvisos } from '../api/normalize'
import type { Api, Aviso, AvisosPage } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
})

vi.mock('../lib/notificaciones', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/notificaciones')>()
  return { ...actual, actualizarBadge: vi.fn(async () => {}), cerrarNotificaciones: vi.fn(async () => {}) }
})

const demo = vi.hoisted(() => ({ abierto: false, ir: vi.fn() }))
vi.mock('../piezas', () => ({
  piezas: () => [{ id: 'demo', avisos: { kind: 'demo', icono: 'calendar', etiqueta: 'Demo', abierto: () => demo.abierto, ir: demo.ir } }],
}))

const { av, abrirAvisos, cerrarAvisos, initAvisos, irAAviso, marcarDestino, marcarTodoLeido, masAvisos, refrescarAvisos } = await import('./avisos')
const { auth, avisosLeidosEvent, init, viewRequest } = await import('./app')
const { pushState } = await import('./push')
const { cerrarNotificaciones } = await import('../lib/notificaciones')
const cerrarMock = vi.mocked(cerrarNotificaciones)

const aviso = (id: number, over: Partial<Aviso> = {}): Aviso => ({
  id, ts: 1_800_000_000 + id, kind: 'done', titulo: `n${id}`, cuerpo: '', session_id: '', pane_id: '', fecha: '', mr: '', tag: '', entregado: true, leido: false, motivo: '', ...over,
})
const page = (items: Aviso[], over: Partial<AvisosPage> = {}): AvisosPage => ({ items, hayMas: false, noLeidos: 0, leidosHasta: 0, ...over })

function api(over: Partial<Api>) {
  init({ getAvisos: vi.fn(async () => page([])), marcarAvisosLeidos: vi.fn(async () => 0), ...over } as unknown as Api)
}

beforeEach(() => {
  Object.assign(av, { open: false, loading: false, loadingMore: false, loaded: false, error: '', items: [], hayMas: false, noLeidos: 0, leidosHasta: 0, nuevosDesde: 0 })
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined })
  cerrarMock.mockClear()
  pushState.endpoint = ''
})

describe('estado de avisos', () => {
  it('carga la primera página y el contador', async () => {
    api({ getAvisos: vi.fn(async () => page([aviso(3), aviso(2)], { noLeidos: 2, leidosHasta: 1, hayMas: true })) })
    await refrescarAvisos()
    expect(av.items.map((a) => a.id)).toEqual([3, 2])
    expect([av.noLeidos, av.leidosHasta, av.hayMas, av.loaded]).toEqual([2, 1, true, true])
  })

  it('guarda el error solo si todavía no había cargado', async () => {
    api({ getAvisos: vi.fn(async () => { throw new Error('x') }) })
    await refrescarAvisos()
    expect(av.error).toMatch(/avisos/)
    av.loaded = true
    av.error = ''
    await refrescarAvisos()
    expect(av.error).toBe('')
  })

  it('al abrir carga, recuerda lo no leído y lo marca como leído', async () => {
    const marcar = vi.fn(async () => 0)
    api({ getAvisos: vi.fn(async () => page([aviso(3), aviso(2), aviso(1)], { noLeidos: 2, leidosHasta: 1 })), marcarAvisosLeidos: marcar })
    await abrirAvisos()
    expect(av.open).toBe(true)
    expect(av.nuevosDesde).toBe(1)
    expect(marcar).toHaveBeenCalledWith(3, undefined)
    expect(av.noLeidos).toBe(0)
    expect(av.leidosHasta).toBe(3)
  })

  it('si marcar falla, el contador vuelve', async () => {
    api({ marcarAvisosLeidos: vi.fn(async () => { throw new Error('x') }) })
    Object.assign(av, { items: [aviso(2)], noLeidos: 1, leidosHasta: 1 })
    await marcarTodoLeido()
    expect(av.noLeidos).toBe(1)
  })

  it('marca todo leído con endpoint push si hay suscripción', async () => {
    const marcar = vi.fn(async () => 0)
    api({ marcarAvisosLeidos: marcar })
    Object.assign(av, { items: [aviso(2)], noLeidos: 1, leidosHasta: 1 })
    pushState.endpoint = 'https://push.test/x'
    await marcarTodoLeido()
    expect(marcar).toHaveBeenCalledWith(2, 'https://push.test/x')
  })

  it('pagina hacia atrás con el id del último', async () => {
    const get = vi.fn(async (_l?: number, antes?: number) => page(antes ? [aviso(1)] : [aviso(3), aviso(2)], { hayMas: !antes }))
    api({ getAvisos: get })
    await refrescarAvisos()
    await masAvisos()
    expect(get).toHaveBeenLastCalledWith(50, 2)
    expect(av.items.map((a) => a.id)).toEqual([3, 2, 1])
    expect(av.hayMas).toBe(false)
  })

  it('tocar uno de una pieza lo deja en manos de la pieza', () => {
    const delaPieza = aviso(5, { kind: 'demo', fecha: '2026-10-28' })
    av.open = true
    irAAviso(delaPieza)
    expect(av.open).toBe(false)
    expect(demo.ir).toHaveBeenCalledWith(delaPieza)
  })

  it('cerrar solo cierra', () => {
    av.open = true
    cerrarAvisos()
    expect(av.open).toBe(false)
  })

  it('al entrar logueado refresca y marca todo leído', async () => {
    const marcar = vi.fn(async () => 0)
    const get = vi.fn(async () => page([aviso(3), aviso(2)], { noLeidos: 2, leidosHasta: 1 }))
    api({ getAvisos: get, marcarAvisosLeidos: marcar })
    initAvisos()
    auth.value = 'ready'
    await nextTick()
    await Promise.resolve()
    expect(get).toHaveBeenCalled()
    expect(marcar).toHaveBeenCalledWith(3, undefined)
    expect(av.noLeidos).toBe(0)
  })

  it('aviso de chat se marca leído al tocarlo', async () => {
    const marcar = vi.fn(async () => 0)
    api({ marcarAvisosDe: marcar })
    Object.assign(av, { loaded: true, items: [aviso(2, { kind: 'cierre' })], noLeidos: 1 })
    irAAviso(av.items[0])
    await Promise.resolve()
    expect(marcar).toHaveBeenCalledWith({ kind: 'cierre' }, undefined)
    expect(viewRequest.value?.view).toBe('board')
  })
})

describe('marcar al abrir un destino', () => {
  it('baja el badge en el momento y avisa al servidor con el filtro', async () => {
    let resolver: (n: number) => void = () => undefined
    const marcar = vi.fn(() => new Promise<number>((r) => (resolver = r)))
    api({ marcarAvisosDe: marcar })
    Object.assign(av, { loaded: true, items: [aviso(3, { session_id: 'abc' }), aviso(2, { session_id: 'otra' }), aviso(1, { session_id: 'abc', leido: true })], noLeidos: 2 })
    const p = marcarDestino({ session_id: 'abc' })
    expect(av.noLeidos).toBe(1)
    expect(av.items.map((a) => a.leido)).toEqual([true, false, true])
    resolver(1)
    await p
    expect(marcar).toHaveBeenCalledWith({ session_id: 'abc' }, undefined)
    expect(av.noLeidos).toBe(1)
  })

  it('sin avisos suyos sin leer no pega al servidor', async () => {
    const marcar = vi.fn(async () => 0)
    api({ marcarAvisosDe: marcar })
    Object.assign(av, { loaded: true, items: [aviso(2, { session_id: 'otra' })], noLeidos: 1 })
    await marcarDestino({ session_id: 'abc' })
    expect(marcar).not.toHaveBeenCalled()
    expect(av.noLeidos).toBe(1)
  })

  it('terminal y kind de pieza filtran por su campo', async () => {
    const marcar = vi.fn(async () => 0)
    api({ marcarAvisosDe: marcar })
    Object.assign(av, { loaded: true, items: [aviso(2, { kind: 'demo', fecha: '2026-10-28' }), aviso(1, { kind: 'terminal', pane_id: 'w1:p2' })], noLeidos: 2 })
    await marcarDestino({ kind: 'demo' })
    await marcarDestino({ pane_id: 'w1:p2' })
    expect(marcar.mock.calls).toEqual([[{ kind: 'demo' }, undefined], [{ pane_id: 'w1:p2' }, undefined]])
    expect(av.noLeidos).toBe(0)
  })

  it('si el servidor falla deja lo optimista', async () => {
    api({ marcarAvisosDe: vi.fn(async () => { throw new Error('x') }) })
    Object.assign(av, { loaded: true, items: [aviso(2, { session_id: 'abc' })], noLeidos: 1 })
    await marcarDestino({ session_id: 'abc' })
    expect(av.noLeidos).toBe(0)
  })

  it('marca destino con endpoint push si hay suscripción', async () => {
    const marcar = vi.fn(async () => 0)
    api({ marcarAvisosDe: marcar })
    Object.assign(av, { loaded: true, items: [aviso(2, { session_id: 'abc' })], noLeidos: 1 })
    pushState.endpoint = 'https://push.test/x'
    await marcarDestino({ session_id: 'abc' })
    expect(marcar).toHaveBeenCalledWith({ session_id: 'abc' }, 'https://push.test/x')
  })
})

describe('cerrar notificaciones al sincronizar', () => {
  beforeAll(() => {
    initAvisos()
  })

  it('refrescar cierra tags cerrables tras cargar', async () => {
    api({ getAvisos: vi.fn(async () => page([aviso(2, { tag: 'x' })], { leidosHasta: 2 })) })
    await refrescarAvisos()
    expect(cerrarMock).toHaveBeenCalledWith({ tags: ['x'] })
  })

  it('refrescar no cierra si no hay tags cerrables', async () => {
    api({ getAvisos: vi.fn(async () => page([aviso(3, { tag: 'y' })], { noLeidos: 1 })) })
    await refrescarAvisos()
    expect(cerrarMock).not.toHaveBeenCalled()
  })

  it('evento avisos leídos con tags cierra y vuelve a cargar', async () => {
    const get = vi.fn(async () => page([]))
    api({ getAvisos: get })
    auth.value = 'ready'
    await nextTick()
    get.mockClear()
    cerrarMock.mockClear()
    avisosLeidosEvent.value = { tags: ['a'], n: 1 }
    await nextTick()
    await Promise.resolve()
    expect(cerrarMock).toHaveBeenCalledWith({ tags: ['a'] })
    expect(get).toHaveBeenCalled()
  })

  it('evento avisos leídos sin tags solo refresca', async () => {
    const get = vi.fn(async () => page([]))
    api({ getAvisos: get })
    auth.value = 'ready'
    await nextTick()
    get.mockClear()
    cerrarMock.mockClear()
    avisosLeidosEvent.value = { tags: [], n: 2 }
    await nextTick()
    await Promise.resolve()
    expect(cerrarMock).not.toHaveBeenCalled()
    expect(get).toHaveBeenCalled()
  })
})

describe('normalizeAvisos', () => {
  it('descarta lo inválido y limita tamaños', () => {
    const out = normalizeAvisos({
      items: [aviso(2), { id: 'x' }, null, { ...aviso(3), kind: 'raro' }, { ...aviso(4), cuerpo: 'a'.repeat(900) }],
      hay_mas: true, no_leidos: 3, leidos_hasta: 1,
    })
    expect(out.items.map((a) => a.id)).toEqual([2, 4])
    expect(out.items[1].cuerpo).toHaveLength(400)
    expect([out.hayMas, out.noLeidos, out.leidosHasta]).toEqual([true, 3, 1])
  })
  it('acepta los kinds de piezas solo si se los pasan', () => {
    const raw = { items: [{ ...aviso(2), kind: 'demo' }] }
    expect(normalizeAvisos(raw).items).toEqual([])
    expect(normalizeAvisos(raw, false, ['demo']).items.map((a) => a.kind)).toEqual(['demo'])
  })
  it('tolera basura', () => {
    expect(normalizeAvisos(null)).toEqual({ items: [], hayMas: false, noLeidos: 0, leidosHasta: 0 })
  })

  it('conserva tag válido y descarta el resto', () => {
    const ok = { ...aviso(1), tag: 'ses-abc_1:2' }
    const out = normalizeAvisos({
      items: [ok, { ...aviso(2), tag: 'a b' }, { ...aviso(3), tag: 'x'.repeat(200) }, { ...aviso(4), tag: 3 }],
    })
    expect(out.items.map((a) => [a.id, a.tag])).toEqual([
      [1, 'ses-abc_1:2'],
      [2, ''],
      [3, ''],
      [4, ''],
    ])
  })
})
