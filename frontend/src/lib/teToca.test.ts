import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { teTocaItems, type TeTocaAgente, type TeTocaInput } from './teToca'

const NOW = Date.parse('2026-11-04T18:00:00.000Z')
const hace = (min: number) => new Date(NOW - min * 60_000).toISOString()

function ag(
  pane: string,
  sid: string,
  extra: Partial<TeTocaAgente> = {},
): TeTocaAgente {
  return {
    pane_id: pane,
    session_id: sid,
    status: 'idle',
    asks_user: false,
    last_activity: hace(10),
    nombre: `WS · ${pane}`,
    hue: 1,
    ...extra,
  }
}

function base(over: Partial<TeTocaInput> = {}): TeTocaInput {
  return {
    agentes: [],
    pedidos: [],
    now: NOW,
    ...over,
  }
}

describe('teTocaItems', () => {
  it('ordena permiso, pregunta y terminada', () => {
    const items = teTocaItems(
      base({
        agentes: [
          ag('a1', 's1', { status: 'done', unread: true, last_activity: hace(1) }),
          ag('a2', 's2', { asks_user: true, last_activity: hace(2) }),
          ag('a3', 's3', { status: 'blocked', last_activity: hace(3) }),
        ],
      }),
    )
    expect(items.map((i) => i.motivo)).toEqual(['permiso', 'pregunta', 'terminada'])
  })

  it('dentro de cada grupo la más vieja primero', () => {
    const items = teTocaItems(
      base({
        agentes: [
          ag('a1', 's1', { status: 'blocked', last_activity: hace(5) }),
          ag('a2', 's2', { status: 'blocked', last_activity: hace(20) }),
          ag('a3', 's3', { asks_user: true, last_activity: hace(30) }),
          ag('a4', 's4', { asks_user: true, last_activity: hace(8) }),
        ],
        pedidos: [
          { id: 'p1', session_id: 's1', pane_id: 'a1', herramienta: 'Bash', entrada: {}, estado: 'abierto', regla: null, creado: hace(5) },
          { id: 'p2', session_id: 's2', pane_id: 'a2', herramienta: 'Bash', entrada: {}, estado: 'abierto', regla: null, creado: hace(20) },
        ],
      }),
    )
    expect(items.map((i) => i.sid)).toEqual(['s2', 's1', 's3', 's4'])
  })

  it('dedupe por sesión con el motivo más urgente', () => {
    const items = teTocaItems(
      base({
        agentes: [ag('a1', 's1', { status: 'blocked', asks_user: true, unread: true })],
        pedidos: [
          { id: 'p1', session_id: 's1', pane_id: 'a1', herramienta: 'Bash', entrada: {}, estado: 'abierto', regla: null, creado: hace(1) },
        ],
      }),
    )
    expect(items).toHaveLength(1)
    expect(items[0].motivo).toBe('permiso')
  })

  it('marca vencido a las 3 h', () => {
    const items = teTocaItems(
      base({
        agentes: [ag('a1', 's1', { status: 'blocked', last_activity: hace(200) })],
        pedidos: [
          {
            id: 'p1',
            session_id: 's1',
            pane_id: 'a1',
            herramienta: 'Bash',
            entrada: {},
            estado: 'abierto',
            regla: null,
            creado: hace(200),
          },
        ],
      }),
    )
    expect(items[0].vencido).toBe(true)
  })

  it('edad del permiso desde creado del pedido', () => {
    const items = teTocaItems(
      base({
        agentes: [ag('a1', 's1', { status: 'blocked', last_activity: hace(1) })],
        pedidos: [
          {
            id: 'p1',
            session_id: 's1',
            pane_id: 'a1',
            herramienta: 'Bash',
            entrada: {},
            estado: 'abierto',
            regla: null,
            creado: hace(45),
          },
        ],
      }),
    )
    expect(items[0].desdeMs).toBe(Date.parse(hace(45)))
  })

  it('una sesión que pregunta entra sin lote, desde su última actividad', () => {
    const r = teTocaItems(base({ agentes: [ag('a1', 's1', { asks_user: true, last_activity: hace(40) })] }))
    expect(r[0].motivo).toBe('pregunta')
    expect(r[0].desdeMs).toBe(Date.parse(hace(40)))
  })

  it('teToca no importa bandeja ni centinela', () => {
    expect(readFileSync(new URL('./teToca.ts', import.meta.url).pathname, 'utf8')).not.toMatch(/bandeja|centinela/i)
  })

  it('terminada solo con unread sin blocked ni pregunta', () => {
    expect(
      teTocaItems(base({ agentes: [ag('a1', 's1', { status: 'working', unread: true })] }))[0]?.motivo,
    ).toBe('terminada')
    expect(teTocaItems(base({ agentes: [ag('a1', 's1', { unread: true, asks_user: true })] }))[0]?.motivo).toBe(
      'pregunta',
    )
  })
})

describe('motivo pedido', () => {
  it('una sesión con pedido pendiente tiene motivo pedido', () => {
    const items = teTocaItems(
      base({ agentes: [ag('p1', 's1')], pedidosPestana: [{ ts: 100, origen: { session_id: 's1' } }] }),
    )
    expect(items[0]).toMatchObject({ sid: 's1', motivo: 'pedido', desdeMs: 100_000 })
  })
  it('el permiso tiene prioridad sobre el pedido', () => {
    const items = teTocaItems(
      base({
        agentes: [ag('p1', 's1', { status: 'blocked' })],
        pedidosPestana: [{ ts: 1, origen: { session_id: 's1' } }],
      }),
    )
    expect(items[0].motivo).toBe('permiso')
  })
  it('el pedido va antes que la pregunta y usa el ts más viejo', () => {
    const items = teTocaItems(
      base({
        agentes: [ag('p1', 's1', { asks_user: true }), ag('p2', 's2')],
        pedidosPestana: [
          { ts: 500, origen: { session_id: 's2' } },
          { ts: 200, origen: { session_id: 's2' } },
        ],
      }),
    )
    expect(items.map((i) => i.motivo)).toEqual(['pedido', 'pregunta'])
    expect(items[0].desdeMs).toBe(200_000)
  })
  it('un pedido vencido no pone la sesión en Te toca', () => {
    const vence = Math.floor(NOW / 1000)
    const items = teTocaItems(
      base({ agentes: [ag('p1', 's1')], pedidosPestana: [{ ts: vence - 600, vence, origen: { session_id: 's1' } }] }),
    )
    expect(items).toEqual([])
    const vigente = teTocaItems(
      base({ agentes: [ag('p1', 's1')], pedidosPestana: [{ ts: vence - 600, vence: vence + 1, origen: { session_id: 's1' } }] }),
    )
    expect(vigente[0]).toMatchObject({ sid: 's1', motivo: 'pedido' })
  })
  it('un pedido sin sesión no genera fila', () => {
    const items = teTocaItems(base({ agentes: [ag('p1', 's1')], pedidosPestana: [{ ts: 1, origen: { session_id: '' } }] }))
    expect(items).toEqual([])
  })
})
