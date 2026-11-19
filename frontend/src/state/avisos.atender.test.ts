import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api, Aviso, AvisosPage } from '../api/types'

const focusHandlers: Array<() => void> = []

vi.hoisted(() => {
  vi.stubGlobal('document', {
    visibilityState: 'visible',
    hasFocus: () => true,
    addEventListener: vi.fn(),
    createElement: (tag: string) => ({
      tagName: tag.toUpperCase(),
      style: {},
      setAttribute() {},
      appendChild() {},
      remove() {},
    }),
  })
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: true, addEventListener() {} }),
    addEventListener: (ev: string, fn: () => void) => {
      if (ev === 'focus') focusHandlers.push(fn)
    },
  })
  vi.stubGlobal('location', { search: '', pathname: '/' })
})

vi.mock('../lib/notificaciones', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/notificaciones')>()
  return { ...actual, actualizarBadge: vi.fn(async () => {}), cerrarNotificaciones: vi.fn(async () => {}) }
})

const { av, initAvisos } = await import('./avisos')
const { auth, init } = await import('./app')
const { openSessionId, sesionAtendida } = await import('./session')
const { desktop } = await import('../lib/viewport')
import * as aLaVista from '../lib/aLaVista'

const aviso = (id: number, over: Partial<Aviso> = {}): Aviso => ({
  id,
  ts: 1_800_000_000 + id,
  kind: 'done',
  titulo: `n${id}`,
  cuerpo: '',
  session_id: '',
  pane_id: '',
  fecha: '',
  mr: '',
  tag: '',
  entregado: true,
  leido: false,
  motivo: '',
  ...over,
})
const page = (items: Aviso[], over: Partial<AvisosPage> = {}): AvisosPage => ({
  items,
  hayMas: false,
  noLeidos: items.filter((a) => !a.leido).length,
  leidosHasta: 0,
  ...over,
})

const sid = '11111111-aaaa-bbbb-cccc-dddddddddddd'

beforeEach(() => {
  desktop.value = true
  openSessionId.value = null
  sesionAtendida.value = null
  vi.spyOn(aLaVista, 'estaALaVista').mockReturnValue(true)
  Object.assign(av, { open: false, loading: false, loadingMore: false, loaded: true, error: '', items: [], hayMas: false, noLeidos: 0, leidosHasta: 0, nuevosDesde: 0 })
  vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => undefined })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('avisos y sesión atendida', () => {
  it('aviso nuevo con sesión abierta no se marca solo por marcarAbiertos', async () => {
    const marcarDe = vi.fn(async () => 0)
    const get = vi.fn(async () => page([aviso(2, { session_id: sid })], { noLeidos: 1 }))
    init({ getAvisos: get, marcarAvisosDe: marcarDe, marcarAvisosLeidos: vi.fn(async () => 0) } as unknown as Api)
    initAvisos()
    auth.value = 'ready'
    await nextTick()
    await Promise.resolve()
    marcarDe.mockClear()
    openSessionId.value = sid
    await nextTick()
    await Promise.resolve()
    expect(marcarDe).not.toHaveBeenCalledWith({ session_id: sid }, expect.anything())
  })

  it('sesionAtendida marca avisos de esa sesión', async () => {
    const marcarDe = vi.fn(async () => 0)
    init({ getAvisos: vi.fn(async () => page([])), marcarAvisosDe: marcarDe, marcarAvisosLeidos: vi.fn(async () => 0) } as unknown as Api)
    initAvisos()
    auth.value = 'ready'
    Object.assign(av, { loaded: true, items: [aviso(2, { session_id: sid })], noLeidos: 1 })
    sesionAtendida.value = { id: sid, n: 1 }
    await nextTick()
    await Promise.resolve()
    expect(marcarDe).toHaveBeenCalledWith({ session_id: sid }, undefined)
  })

  it('focus no marca todos los avisos (no refrescarAlEntrar)', async () => {
    const marcarTodo = vi.fn(async () => 0)
    const get = vi.fn(async () => page([aviso(3), aviso(2)], { noLeidos: 2, leidosHasta: 1 }))
    init({ getAvisos: get, marcarAvisosLeidos: marcarTodo, marcarAvisosDe: vi.fn(async () => 0) } as unknown as Api)
    initAvisos()
    auth.value = 'ready'
    await nextTick()
    await Promise.resolve()
    marcarTodo.mockClear()
    get.mockClear()
    for (const fn of focusHandlers) fn()
    await Promise.resolve()
    expect(marcarTodo).not.toHaveBeenCalled()
    expect(get).not.toHaveBeenCalled()
  })
})
