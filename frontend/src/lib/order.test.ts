import { describe, expect, it } from 'vitest'
import type { Agent, AgentStatus, Workspace } from '../api/types'
import {
  aplicarOrdenManual,
  aplicarOrdenPestanas,
  agentIsActive,
  claveGrupoPestanas,
  findFirst,
  idDePane,
  indiceVecinoQuieto,
  moverEnOrden,
  ordenTrasArrastreQuietos,
  sortAgents,
  sortWorkspaces,
  trackAttention,
  wsEsActivoParaOrden,
  wsFlags,
  wsIsActive,
  wsNeedsUser,
  agentEsActivoParaOrden,
  type AttentionSince,
} from './order'

const ag = (pane: string, status: AgentStatus, mins: number, asks = false, unread = false): Agent => ({
  pane_id: pane,
  kind: 'claude',
  status,
  session_id: pane,
  title: pane,
  doing: '',
  pending: '',
  asks_user: asks,
  unread,
  last_activity: new Date(1_700_000_000_000 - mins * 60_000).toISOString(),
})
const ws = (id: string, number: number, agents: Agent[], status: AgentStatus = 'idle'): Workspace => ({
  id,
  number,
  label: id,
  pinned: false,
  status,
  tabs: [{ id: `${id}:t`, label: '1', agents }],
})
const ids = (l: Workspace[], since: AttentionSince = new Map()) => sortWorkspaces(l, since).map((w) => w.id)

describe('sortWorkspaces', () => {
  it('sin atención, el usado más recientemente arriba', () => {
    const list = [ws('c', 3, [ag('c', 'idle', 1)]), ws('a', 1, [ag('a', 'idle', 90)]), ws('b', 2, [ag('b', 'idle', 500)])]
    expect(ids(list)).toEqual(['c', 'a', 'b'])
  })
  it('cuenta la sesión más reciente del workspace', () => {
    const list = [ws('a', 1, [ag('a1', 'idle', 300), ag('a2', 'idle', 2)]), ws('b', 2, [ag('b', 'idle', 10)])]
    expect(ids(list)).toEqual(['a', 'b'])
  })
  it('a igual hora, orden del tablero', () => {
    const list = [ws('a', 1, [ag('a', 'idle', 5)]), ws('c', 3, [ag('c', 'working', 0)], 'working'), ws('b', 2, [ag('b', 'working', 0)], 'working')]
    expect(ids(list)).toEqual(['b', 'c', 'a'])
  })
  it('las que necesitan al usuario siguen arriba de las que trabajan', () => {
    const list = [ws('a', 1, [ag('a', 'working', 0)], 'working'), ws('b', 2, [ag('b', 'idle', 5, false, true)])]
    expect(ids(list)).toEqual(['b', 'a'])
  })
  it('bloqueado, pregunta y respuesta nueva van arriba; el último en pedir primero', () => {
    const list = [
      ws('a', 1, [ag('a', 'idle', 1)]),
      ws('b', 2, [ag('b', 'blocked', 1)], 'blocked'),
      ws('c', 3, [ag('c', 'idle', 1, true)]),
      ws('d', 4, [ag('d', 'idle', 1, false, true)]),
    ]
    const since: AttentionSince = new Map([['b', 100], ['c', 300], ['d', 200]])
    expect(ids(list, since)).toEqual(['c', 'd', 'b', 'a'])
  })
  it('el orden entre los que piden no cambia por cambios ajenos', () => {
    const since: AttentionSince = new Map()
    const l1 = [ws('a', 1, [ag('a', 'idle', 1, true)]), ws('b', 2, [ag('b', 'idle', 1)]), ws('c', 3, [ag('c', 'idle', 1)])]
    trackAttention(l1, since, 1000)
    const l2 = [ws('a', 1, [ag('a', 'idle', 1, true)]), ws('b', 2, [ag('b', 'idle', 1, true)]), ws('c', 3, [ag('c', 'working', 0)], 'working')]
    trackAttention(l2, since, 2000)
    expect(ids(l2, since)).toEqual(['b', 'a', 'c'])
    const l3 = [...l2.slice(0, 2), ws('c', 3, [ag('c', 'idle', 0)])]
    trackAttention(l3, since, 3000)
    expect(ids(l3, since)).toEqual(['b', 'a', 'c'])
  })
  it('trackAttention olvida al que ya no pide', () => {
    const since: AttentionSince = new Map()
    trackAttention([ws('a', 1, [ag('a', 'idle', 1, true)])], since, 1)
    trackAttention([ws('a', 1, [ag('a', 'idle', 1)])], since, 2)
    expect(since.size).toBe(0)
  })
  it('empates estables por número y sin mutar la lista', () => {
    const tie = [ws('x', 2, []), ws('y', 1, [])]
    expect(ids(tie)).toEqual(['y', 'x'])
    expect(tie[0].id).toBe('x')
  })
  it('el fijado va primero aunque esté quieto y otro pida atención', () => {
    const l = [ws('a', 1, [ag('a', 'blocked', 1)]), { ...ws('fijo', 2, [ag('f', 'idle', 90)]), pinned: true }]
    expect(ids(l)).toEqual(['fijo', 'a'])
  })
  it('un workspace bloqueado sin agentes visibles igual cuenta como atención', () => {
    const l = [ws('a', 1, [ag('a', 'idle', 1)]), ws('b', 2, [], 'blocked')]
    expect(ids(l)[0]).toBe('b')
  })
})

describe('aplicarOrdenManual', () => {
  const list = [ws('a', 1, [ag('a', 'idle', 5)]), ws('b', 2, [ag('b', 'idle', 1)]), ws('c', 3, [ag('c', 'idle', 90)])]
  it('sin orden guardado igual que el automático', () => {
    expect(aplicarOrdenManual(sortWorkspaces(list), [], (w) => w.id).map((w) => w.id)).toEqual(ids(list))
  })
  it('tarjetas nuevas arriba en orden automático', () => {
    const auto = sortWorkspaces(list)
    expect(aplicarOrdenManual(auto, ['b'], (w) => w.id).map((w) => w.id)).toEqual(['a', 'c', 'b'])
  })
  it('ignora ids viejos que ya no existen', () => {
    expect(aplicarOrdenManual(sortWorkspaces(list), ['z', 'b', 'a'], (w) => w.id).map((w) => w.id)).toEqual(['c', 'b', 'a'])
  })
  it('las activas van arriba y las quietas siguen el orden manual', () => {
    const since: AttentionSince = new Map()
    const base = [ws('quiet', 1, [ag('q', 'idle', 5)]), ws('asks', 2, [ag('a', 'idle', 1, true)])]
    trackAttention(base, since, 100)
    const manual = ['quiet', 'asks']
    const once = aplicarOrdenManual(sortWorkspaces(base, since), manual, (w) => w.id)
    expect(once.map((w) => w.id)).toEqual(['asks', 'quiet'])
    trackAttention(base, since, 200)
    const sinAsks = [ws('quiet', 1, [ag('q', 'idle', 5)]), ws('asks', 2, [ag('a', 'idle', 1)])]
    const again = aplicarOrdenManual(sortWorkspaces(sinAsks, since), manual, (w) => w.id)
    expect(again.map((w) => w.id)).toEqual(['quiet', 'asks'])
  })

  it('sin leer no sube arriba y queda en orden manual', () => {
    const since: AttentionSince = new Map()
    const base = [
      ws('quiet', 1, [ag('q', 'idle', 5)]),
      ws('unread', 2, [ag('u', 'idle', 1, false, true)]),
    ]
    trackAttention(base, since, 100)
    const manual = ['quiet', 'unread']
    const ordenado = aplicarOrdenManual(sortWorkspaces(base, since), manual, (w) => w.id)
    expect(ordenado.map((w) => w.id)).toEqual(['quiet', 'unread'])
    expect(wsEsActivoParaOrden(base[1]!)).toBe(false)
  })

  it('pregunta, bloqueado y working sí suben sobre el orden manual', () => {
    const list = [
      ws('q1', 1, [ag('q1', 'idle', 5)]),
      ws('ask', 2, [ag('a', 'idle', 1, true)]),
      ws('blk', 3, [ag('b', 'blocked', 1)], 'blocked'),
      ws('w', 4, [ag('w', 'working', 0)], 'working'),
    ]
    expect(aplicarOrdenManual(sortWorkspaces(list), ['q1', 'ask', 'blk', 'w'], (w) => w.id).map((w) => w.id)).toEqual([
      'ask',
      'blk',
      'w',
      'q1',
    ])
  })

  it('las working van arriba de las quietas manuales', () => {
    const list = [
      ws('q1', 1, [ag('q1', 'idle', 5)]),
      ws('q2', 2, [ag('q2', 'idle', 90)]),
      ws('w', 3, [ag('w', 'working', 0)], 'working'),
    ]
    expect(aplicarOrdenManual(sortWorkspaces(list), ['q2', 'q1'], (w) => w.id).map((w) => w.id)).toEqual([
      'w',
      'q2',
      'q1',
    ])
  })
})

describe('ordenTrasArrastreQuietos', () => {
  it('mueve quietos en el orden guardado sin cambiar activos', () => {
    const visual = ['a1', 'q2', 'q1']
    const prev = ['q1', 'q2', 'a1']
    expect(ordenTrasArrastreQuietos(visual, (id) => id === 'a1', prev)).toEqual(['q2', 'q1', 'a1'])
  })
})

describe('indiceVecinoQuieto', () => {
  const activo = new Set([1])
  const esAct = (i: number) => activo.has(i)

  it('sube al quieto anterior saltando activos', () => {
    expect(indiceVecinoQuieto(3, -1, 4, esAct)).toBe(2)
    expect(indiceVecinoQuieto(2, -1, 4, esAct)).toBe(0)
    expect(indiceVecinoQuieto(0, -1, 4, esAct)).toBe(null)
  })

  it('baja al quieto siguiente saltando activos', () => {
    expect(indiceVecinoQuieto(0, 1, 4, esAct)).toBe(2)
    expect(indiceVecinoQuieto(2, 1, 4, esAct)).toBe(3)
    expect(indiceVecinoQuieto(3, 1, 4, esAct)).toBe(null)
  })
})

describe('moverEnOrden', () => {
  it('mueve un id', () => {
    expect(moverEnOrden(['a', 'b', 'c'], 0, 2)).toEqual(['b', 'c', 'a'])
    expect(moverEnOrden(['a', 'b', 'c'], 2, 0)).toEqual(['c', 'a', 'b'])
  })
  it('fuera de rango no cambia', () => {
    expect(moverEnOrden(['a'], 0, 0)).toEqual(['a'])
    expect(moverEnOrden(['a', 'b'], -1, 1)).toEqual(['a', 'b'])
  })
})

describe('aplicarOrdenPestanas', () => {
  const tabAgents = (panes: string[]) => panes.map((p) => ag(p, 'idle', 5))

  it('sin orden guardado igual que el automático', () => {
    const list = tabAgents(['a', 'b', 'c'])
    expect(aplicarOrdenPestanas(list, []).map(idDePane)).toEqual(['a', 'b', 'c'])
  })

  it('pestañas nuevas arriba en orden automático', () => {
    const auto = tabAgents(['a', 'b', 'c'])
    expect(aplicarOrdenPestanas(auto, ['b']).map(idDePane)).toEqual(['a', 'c', 'b'])
  })

  it('activas arriba y quietas en orden manual', () => {
    const since: AttentionSince = new Map()
    const base = tabAgents(['quiet', 'asks'])
    base[1] = ag('asks', 'idle', 1, true)
    const manual = ['quiet', 'asks']
    expect(aplicarOrdenPestanas(sortAgents(base, since), manual).map(idDePane)).toEqual(['asks', 'quiet'])
    base[1] = ag('asks', 'idle', 1)
    expect(aplicarOrdenPestanas(sortAgents(base, since), manual).map(idDePane)).toEqual(['quiet', 'asks'])
  })

  it('detecta pestaña activa', () => {
    expect(agentIsActive(ag('w', 'working', 0))).toBe(true)
    expect(agentIsActive(ag('q', 'idle', 1, true))).toBe(true)
    expect(agentIsActive(ag('q', 'idle', 1))).toBe(false)
  })

  it('sin leer no cuenta activa para orden de pestañas', () => {
    expect(agentEsActivoParaOrden(ag('u', 'idle', 1, false, true))).toBe(false)
    expect(agentEsActivoParaOrden(ag('a', 'idle', 1, true))).toBe(true)
    const base = [ag('quiet', 'idle', 5), ag('unread', 'idle', 1, false, true)]
    expect(aplicarOrdenPestanas(sortAgents(base), ['quiet', 'unread']).map(idDePane)).toEqual(['quiet', 'unread'])
  })
})

describe('wsIsActive', () => {
  it('working cuenta como activa', () => {
    expect(wsIsActive(ws('w', 1, [ag('w', 'working', 0)], 'working'))).toBe(true)
  })
})

describe('claveGrupoPestanas', () => {
  it('une tarjeta y tab con dos puntos', () => {
    expect(claveGrupoPestanas('wF', 'wF:t2')).toBe('wF:wF:t2')
  })
})

describe('findFirst', () => {
  const list = [
    ws('w1', 1, [ag('p1', 'working', 1)], 'working'),
    ws('w2', 2, [ag('p2', 'blocked', 9, true)], 'blocked'),
    ws('w3', 3, [ag('p3', 'idle', 2, true, true)]),
  ]
  const since: AttentionSince = new Map([['w2', 10], ['w3', 20]])
  it('devuelve la primera sesión del estado según el orden del tablero', () => {
    expect(findFirst(list, 'blocked', since)).toEqual({ wsId: 'w2', paneId: 'p2' })
    expect(findFirst(list, 'asks', since)).toEqual({ wsId: 'w3', paneId: 'p3' })
    expect(findFirst(list, 'unread', since)).toEqual({ wsId: 'w3', paneId: 'p3' })
    expect(findFirst(list, 'working', since)).toEqual({ wsId: 'w1', paneId: 'p1' })
  })
  it('null si no hay', () => {
    expect(findFirst([ws('z', 1, [ag('q', 'idle', 1)])], 'blocked', since)).toBeNull()
  })
})

describe('pregunta pendiente (marcada como leída)', () => {
  const pend = (pane: string): Agent => ({ ...ag(pane, 'idle', 1, false), pendiente: true })
  it('no cuenta como pregunta ni pide atención', () => {
    const w = ws('p', 1, [pend('a')])
    expect(wsFlags(w).asks).toBe(false)
    expect(wsNeedsUser(w)).toBe(false)
    expect(agentEsActivoParaOrden(pend('a'))).toBe(false)
  })
  it('no sube la tarjeta por encima de una que sí pregunta', () => {
    const list = [ws('pend', 1, [pend('a')]), ws('asks', 2, [ag('b', 'idle', 9, true)])]
    expect(sortWorkspaces(list, new Map()).map((w) => w.id)).toEqual(['asks', 'pend'])
  })
})
