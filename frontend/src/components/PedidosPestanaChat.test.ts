// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api, PedidoPestana } from '../api/types'

vi.hoisted(() => {
  window.matchMedia = (() => ({ matches: false, addEventListener() {}, removeEventListener() {} })) as unknown as typeof window.matchMedia
})

vi.mock('../state/terminales', () => ({
  openTerminal: vi.fn(),
  closeTerminal: vi.fn(),
  openTerminalId: { value: null },
}))

const { init } = await import('../state/app')
const { _resetPedidosPestana, aplicarPedidoPestanaSse, pedidosPestana } = await import('../state/pedidosPestana')
const { default: PedidoPestanaCard } = await import('./PedidoPestanaCard.vue')
const { default: PedidosPestanaChat } = await import('./PedidosPestanaChat.vue')

const A = 'a', B = 'b', C = 'c'
const ped = (o: { id: string; ts: number; sid: string }): PedidoPestana => ({
  id: o.id,
  carpeta: '/proyecto/foo',
  mensaje: 'Hola',
  origen: { pane_id: 'w1:p1', nombre: 'Sesión A', session_id: o.sid },
  ts: o.ts,
  vence: Math.floor(Date.now() / 1000) + 600,
})

const abrir = vi.fn(async (_id?: string) => ({ ok: true, pane_id: 'w1:p2', pegado: true }))

beforeEach(() => {
  _resetPedidosPestana()
  abrir.mockClear()
  init({ getPedidosPestana: vi.fn(async () => []), abrirPedidoPestana: abrir, rechazarPedidoPestana: vi.fn() } as unknown as Api)
})

describe('PedidosPestanaChat', () => {
  it('muestra solo los pedidos de su sesión, el más viejo arriba', () => {
    pedidosPestana.items = [ped({ id: A, ts: 20, sid: 's1' }), ped({ id: B, ts: 10, sid: 's1' }), ped({ id: C, ts: 5, sid: 's2' })]
    const w = mount(PedidosPestanaChat, { props: { sessionId: 's1' } })
    expect(w.findAllComponents(PedidoPestanaCard).map((c) => c.props('pedido').id)).toEqual([B, A])
    expect(w.attributes('role')).toBe('region')
    expect(w.attributes('aria-label')).toBe('Pedidos de esta sesión')
  })

  it('un pedido sin sesión de origen no aparece en ningún chat', () => {
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: '' })]
    const w = mount(PedidosPestanaChat, { props: { sessionId: 's1' } })
    expect(w.findAllComponents(PedidoPestanaCard)).toHaveLength(0)
  })

  it('Abrir en el chat llama al estado y al resolverse desaparece', async () => {
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's1' })]
    const w = mount(PedidosPestanaChat, { props: { sessionId: 's1' } })
    await w.find('button.primary').trigger('click')
    expect(abrir.mock.calls[0]?.[0]).toBe(A)
    aplicarPedidoPestanaSse(A, 'abierto')
    await nextTick()
    await nextTick()
    expect(w.findAllComponents(PedidoPestanaCard)).toHaveLength(0)
  })

  it('con 0 pedidos el grupo sigue montado y marcado vacío; el primer pedido entra en el mismo grupo', async () => {
    const w = mount(PedidosPestanaChat, { props: { sessionId: 's1' } })
    const raiz = w.element
    expect(raiz.getAttribute('role')).toBe('region')
    expect(raiz.classList.contains('vacio')).toBe(true)
    expect(w.findAllComponents(PedidoPestanaCard)).toHaveLength(0)
    pedidosPestana.items = [ped({ id: A, ts: 1, sid: 's1' })]
    await nextTick()
    expect(w.element).toBe(raiz)
    expect(raiz.classList.contains('vacio')).toBe(false)
    expect(w.findAllComponents(PedidoPestanaCard)).toHaveLength(1)
  })
})
