import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import type { Agent, Board } from '../api/types'
import { agentesTeToca, teTocaItems } from './teToca'
import {
  asignarCeldas,
  celdasQueTerminan,
  estadosCeldas,
  gruposPanel,
  debeFundirTextoResumen,
  debeRetenerResumen,
  opcionesApiladas,
  partesResumen,
  sesionesNotch,
  textoResumen,
  type Asignacion,
} from './notchCeldas'

describe('debeRetenerResumen', () => {
  it('1 trabajando → todo en 0', () => {
    expect(debeRetenerResumen({ teToca: 0, trabajando: 1, termino: 0 }, { teToca: 0, trabajando: 0, termino: 0 })).toBe(true)
  })

  it('2→1 trabajando', () => {
    expect(debeRetenerResumen({ teToca: 0, trabajando: 2, termino: 0 }, { teToca: 0, trabajando: 1, termino: 0 })).toBe(true)
  })

  it('trabajando baja pero teToca sube → no retiene', () => {
    expect(debeRetenerResumen({ teToca: 0, trabajando: 2, termino: 0 }, { teToca: 1, trabajando: 1, termino: 0 })).toBe(false)
  })

  it('trabajando sube → no retiene', () => {
    expect(debeRetenerResumen({ teToca: 0, trabajando: 1, termino: 0 }, { teToca: 0, trabajando: 2, termino: 0 })).toBe(false)
  })

  it('iguales → no retiene', () => {
    expect(debeRetenerResumen({ teToca: 1, trabajando: 2, termino: 0 }, { teToca: 1, trabajando: 2, termino: 0 })).toBe(false)
  })
})

describe('opcionesApiladas', () => {
  it('dos opciones cortas → fila', () => {
    expect(opcionesApiladas(['Sí', 'No'])).toBe(false)
  })

  it('tres opciones cortas → apiladas', () => {
    expect(opcionesApiladas(['A', 'B', 'C'])).toBe(true)
  })

  it('dos opciones con una larga → apiladas', () => {
    expect(opcionesApiladas(['Sí', 'Reescribir el historial de la rama'])).toBe(true)
  })
})

const NOW = Date.parse('2026-11-04T18:00:00Z')
const hace = (min: number) => new Date(NOW - min * 60_000).toISOString()

function ag(pane: string, sid: string | null, over: Partial<Agent> = {}): Agent {
  return {
    pane_id: pane,
    kind: 'claude',
    status: 'idle',
    session_id: sid,
    title: 't-' + pane,
    doing: '',
    pending: '',
    asks_user: false,
    last_activity: hace(30),
    ...over,
  }
}

function board(agents: Agent[], over: Partial<Board> = {}): Board {
  return {
    updated_at: hace(0),
    focused_tab_id: null,
    self_pane_id: null,
    workspaces: [
      {
        id: 'w1',
        number: 1,
        label: 'Acme',
        status: 'idle',
        tabs: agents.map((agent, i) => ({
          id: `t${i}`,
          label: String(i + 1),
          agents: [agent],
        })),
      },
    ],
    terminales: 'ok',
    conflictos: [],
    caidos: [],
    ...over,
  }
}

function items(b: Board) {
  return teTocaItems({ agentes: agentesTeToca(b), pedidos: [], now: NOW })
}

describe('notchCeldas', () => {
  it('pinta cada estado según teToca y el estado efectivo', () => {
    const b = board([
      ag('p1', 's1', { status: 'blocked' }),
      ag('p2', 's2', { asks_user: true }),
      ag('p3', 's3', { status: 'working' }),
      ag('p4', 's4', { fondo: [{ id: 'f', tipo: 'cursor', texto: 'x', desde: 1 }] }),
      ag('p5', 's5', { unread: true }),
      ag('p6', 's6'),
    ])
    const s = sesionesNotch({ board: b, items: items(b) })
    expect(Object.fromEntries(s.map((x) => [x.pane_id, x.estado]))).toEqual({
      p1: 'te-toca',
      p2: 'te-toca',
      p3: 'trabajando',
      p4: 'trabajando',
      p5: 'termino',
      p6: 'tranquila',
    })
    expect(s[0].donde).toBe('Acme · tab 1')
  })

  it('lleva la cantidad de tarjetas de pregunta de cada sesión', () => {
    const b = board([ag('p1', 's1', { asks_user: true, preguntas: 2 }), ag('p2', 's2')])
    expect(sesionesNotch({ board: b, items: items(b) }).map((x) => x.preguntas)).toEqual([2, 0])
  })

  it('deja afuera al pane propio y a los agentes sin sesión', () => {
    const b = board([ag('p1', 's1'), ag('self', 'sself'), ag('p9', null)], { self_pane_id: 'self' })
    expect(sesionesNotch({ board: b, items: items(b) }).map((x) => x.pane_id)).toEqual(['p1'])
  })

  it('funciona sin clave centinela', () => {
    const b = board([ag('p1', 's1')])
    expect(() => sesionesNotch({ board: b, items: items(b) })).not.toThrow()
  })

  it('no importa lib/bandeja', () => {
    expect(readFileSync(new URL('./notchCeldas.ts', import.meta.url).pathname, 'utf8')).not.toMatch(/['"]\.\/bandeja['"]/)
  })

  it('la primera vez llena las celdas con te toca primero', () => {
    const b = board([
      ag('p1', 's1', { status: 'working', last_activity: hace(1) }),
      ag('p2', 's2', { status: 'blocked' }),
    ])
    const s = sesionesNotch({ board: b, items: items(b) })
    expect(asignarCeldas([], s)).toEqual(['p2', 'p1', null, null, null, null])
  })

  it('cada sesión conserva su celda aunque cambie de estado', () => {
    const b1 = board([ag('p1', 's1', { status: 'blocked' }), ag('p2', 's2', { status: 'working' })])
    const a1 = asignarCeldas([], sesionesNotch({ board: b1, items: items(b1) }))
    const b2 = board([ag('p2', 's2', { status: 'blocked' }), ag('p1', 's1', { status: 'working' })])
    expect(asignarCeldas(a1, sesionesNotch({ board: b2, items: items(b2) }))).toEqual(a1)
  })

  it('la celda de una sesión que se fue la toma la próxima que aparece', () => {
    const b = board([ag('a', 'sa'), ag('c', 'sc'), ag('d', 'sd')])
    expect(asignarCeldas(['a', 'b', 'c', null, null, null], sesionesNotch({ board: b, items: items(b) }))).toEqual([
      'a',
      'd',
      'c',
      null,
      null,
      null,
    ])
  })

  it('con más de 6 entran te toca, trabajando y las más recientes, y el resto se cuenta', () => {
    const agents = [
      ag('t', 'st', { status: 'blocked', last_activity: hace(300) }),
      ag('w', 'sw', { status: 'working', last_activity: hace(200) }),
      ...[1, 2, 3, 4, 5, 6].map((n) => ag(`q${n}`, `sq${n}`, { last_activity: hace(n) })),
    ]
    const b = board(agents)
    const s = sesionesNotch({ board: b, items: items(b) })
    const a = asignarCeldas([], s)
    expect(a).toEqual(['t', 'w', 'q1', 'q2', 'q3', 'q4'])
    const g = gruposPanel(a, s)
    expect(g.otras.map((x) => x.pane_id).sort()).toEqual(['q1', 'q2', 'q3', 'q4', 'q5', 'q6'])
    expect(g.fuera).toBe(g.otras.length)
  })

  it('con más de 6, la que ya tenía celda y sigue elegida no se mueve', () => {
    const agents = [
      ag('t', 'st', { status: 'blocked', last_activity: hace(300) }),
      ag('w', 'sw', { status: 'working', last_activity: hace(200) }),
      ...[1, 2, 3, 4, 5, 6].map((n) => ag(`q${n}`, `sq${n}`, { last_activity: hace(n) })),
    ]
    const b = board(agents)
    const s = sesionesNotch({ board: b, items: items(b) })
    const prev: Asignacion = ['q4', null, null, null, null, null]
    expect(asignarCeldas(prev, s)).toEqual(['q4', 't', 'w', 'q1', 'q2', 'q3'])
  })

  it('una sesión recién contestada se ve trabajando', () => {
    const b = board([ag('p1', 's1', { asks_user: true })])
    expect(sesionesNotch({ board: b, items: items(b), enviadas: new Set(['s1']) })[0].estado).toBe('trabajando')
  })

  it('motivo pedido va a te toca aunque la sesión tenga una respuesta enviada', () => {
    const b = board([ag('p1', 's1')])
    const it = teTocaItems({
      agentes: agentesTeToca(b),
      pedidos: [],
      pedidosPestana: [{ ts: 1, origen: { session_id: 's1' } }],
      now: NOW,
    })
    expect(sesionesNotch({ board: b, items: it, enviadas: new Set(['s1']) })[0].estado).toBe('te-toca')
  })

  it('estadosCeldas marca vacía la celda sin sesión', () => {
    const b = board([ag('p1', 's1', { status: 'blocked' })])
    const s = sesionesNotch({ board: b, items: items(b) })
    expect(estadosCeldas(['p1', null, null, null, null, null], s)).toEqual([
      'te-toca',
      'vacia',
      'vacia',
      'vacia',
      'vacia',
      'vacia',
    ])
  })

  it('debeFundirTextoResumen: solo si cambia el texto y no es soft', () => {
    expect(debeFundirTextoResumen('', '3 te tocan · 2 trabajando', false)).toBe(false)
    expect(debeFundirTextoResumen('3 te tocan · 2 trabajando', '3 te tocan · 2 trabajando', false)).toBe(false)
    expect(debeFundirTextoResumen('2 te tocan', '3 te tocan', false)).toBe(true)
    expect(debeFundirTextoResumen('2 te tocan', '3 te tocan', true)).toBe(false)
  })

  it('arma la línea del notch cerrado', () => {
    expect(textoResumen({ teToca: 2, trabajando: 3, termino: 1 })).toBe('2 te tocan · 3 trabajando · 1 terminó')
    expect(textoResumen({ teToca: 1, trabajando: 0, termino: 2 })).toBe('1 te toca · 2 terminaron')
    expect(textoResumen({ teToca: 0, trabajando: 0, termino: 0 })).toBe('Todo tranquilo')
    expect(partesResumen({ teToca: 1, trabajando: 2, termino: 0 })).toEqual([
      { texto: '1 te toca', alerta: true },
      { texto: '2 trabajando', alerta: false },
    ])
  })

  it('celdasQueTerminan devuelve solo las que pasan a terminó', () => {
    expect(celdasQueTerminan(['trabajando', 'termino', 'vacia'], ['termino', 'termino', 'termino'])).toEqual([0, 2])
  })

  describe('gruposPanel otras', () => {
    function paneIds(g: ReturnType<typeof gruposPanel>) {
      return [...g.teToca, ...g.trabajando, ...g.termino, ...g.otras].map((x) => x.pane_id)
    }

    it('una sesión tranquila con celda aparece en otras', () => {
      const b = board([
        ag('w', 'sw', { status: 'working', last_activity: hace(1) }),
        ag('q', 'sq', { last_activity: hace(5) }),
      ])
      const s = sesionesNotch({ board: b, items: items(b) })
      const a: Asignacion = ['w', 'q', null, null, null, null]
      const g = gruposPanel(a, s)
      expect(g.trabajando.map((x) => x.pane_id)).toEqual(['w'])
      expect(g.otras.map((x) => x.pane_id)).toEqual(['q'])
      expect(g.otras[0].estado).toBe('tranquila')
    })

    it('una sesión sin celda (más de 6) aparece en otras', () => {
      const agents = [
        ag('t', 'st', { status: 'blocked', last_activity: hace(300) }),
        ag('w', 'sw', { status: 'working', last_activity: hace(200) }),
        ...[1, 2, 3, 4, 5, 6].map((n) => ag(`q${n}`, `sq${n}`, { last_activity: hace(n) })),
      ]
      const b = board(agents)
      const s = sesionesNotch({ board: b, items: items(b) })
      const a = asignarCeldas([], s)
      const g = gruposPanel(a, s)
      const ids = g.otras.map((x) => x.pane_id)
      expect(ids).toContain('q5')
      expect(ids).toContain('q6')
    })

    it('ninguna sesión aparece dos veces entre los cuatro grupos', () => {
      const agents = [
        ag('t', 'st', { status: 'blocked', last_activity: hace(300) }),
        ag('w', 'sw', { status: 'working', last_activity: hace(200) }),
        ...[1, 2, 3, 4, 5, 6].map((n) => ag(`q${n}`, `sq${n}`, { last_activity: hace(n) })),
      ]
      const b = board(agents)
      const s = sesionesNotch({ board: b, items: items(b) })
      const g = gruposPanel(asignarCeldas([], s), s)
      const ids = paneIds(g)
      expect(new Set(ids).size).toBe(ids.length)
      expect(ids.length).toBe(s.length)
    })

    it('otras va ordenada por actividad más reciente primero', () => {
      const b = board([
        ag('w', 'sw', { status: 'working', last_activity: hace(1) }),
        ag('o1', 'so1', { last_activity: hace(10) }),
        ag('o2', 'so2', { last_activity: hace(2) }),
      ])
      const s = sesionesNotch({ board: b, items: items(b) })
      const a: Asignacion = ['w', 'o1', 'o2', null, null, null]
      const g = gruposPanel(a, s)
      expect(g.otras.map((x) => x.pane_id)).toEqual(['o2', 'o1'])
    })

    it('fuera coincide con otras.length', () => {
      const agents = [
        ag('t', 'st', { status: 'blocked', last_activity: hace(300) }),
        ag('w', 'sw', { status: 'working', last_activity: hace(200) }),
        ...[1, 2, 3, 4, 5, 6].map((n) => ag(`q${n}`, `sq${n}`, { last_activity: hace(n) })),
      ]
      const b = board(agents)
      const s = sesionesNotch({ board: b, items: items(b) })
      const g = gruposPanel(asignarCeldas([], s), s)
      expect(g.fuera).toBe(g.otras.length)
    })
  })
})
