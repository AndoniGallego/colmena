import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Agent, Board } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/notch' })
})

const { boardState } = await import('./app')
const { asignacion, abrirColmena, abrirNotas, abrirSesion, alternarPanel, celdas, cerrarNotas, modo, setPuente } = await import('./notch')

const NOW = Date.parse('2026-11-04T18:00:00Z')
const hace = (min: number) => new Date(NOW - min * 60_000).toISOString()

function ag(pane: string, sid: string, over: Partial<Agent> = {}): Agent {
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

beforeEach(() => {
  modo.value = 'cerrado'
  boardState.value = { ...boardState.value, board: null, connection: 'live' }
})

describe('state/notch', () => {
  it('las celdas siguen al tablero y cada sesión conserva su lugar', async () => {
    boardState.value = {
      ...boardState.value,
      board: board([ag('p1', 's1', { status: 'blocked' }), ag('p2', 's2', { status: 'working' })]),
    }
    await nextTick()
    const antes = [...asignacion.value]
    boardState.value = {
      ...boardState.value,
      board: board([ag('p2', 's2', { status: 'blocked' }), ag('p1', 's1')]),
    }
    await nextTick()
    expect(asignacion.value).toEqual(antes)
    expect(celdas.value[antes.indexOf('p2')]).toBe('te-toca')
  })

  it('abrir una sesión pasa por el puente', () => {
    const p = { enPrograma: true, tamano: vi.fn(), forma: vi.fn(), arrastrar: vi.fn(), abrirColmena: vi.fn(), aviso: vi.fn() }
    setPuente(p)
    abrirSesion('s1')
    abrirColmena()
    expect(p.abrirColmena.mock.calls).toEqual([['s1'], [null]])
  })

  it('abrir sesión con panel abierto colapsa el notch', () => {
    const p = { enPrograma: true, tamano: vi.fn(), forma: vi.fn(), arrastrar: vi.fn(), abrirColmena: vi.fn(), aviso: vi.fn() }
    setPuente(p)
    modo.value = 'panel'
    abrirSesion('s1')
    expect(modo.value).toBe('cerrado')
    expect(p.abrirColmena).toHaveBeenCalledWith('s1')
  })

  it('abrir Colmena con panel abierto colapsa el notch', () => {
    const p = { enPrograma: true, tamano: vi.fn(), forma: vi.fn(), arrastrar: vi.fn(), abrirColmena: vi.fn(), aviso: vi.fn() }
    setPuente(p)
    modo.value = 'panel'
    abrirColmena()
    expect(modo.value).toBe('cerrado')
    expect(p.abrirColmena).toHaveBeenCalledWith(null)
  })

  it('abrir Colmena con aviso visible no cierra el aviso', () => {
    const p = { enPrograma: true, tamano: vi.fn(), forma: vi.fn(), arrastrar: vi.fn(), abrirColmena: vi.fn(), aviso: vi.fn() }
    setPuente(p)
    modo.value = 'aviso'
    abrirColmena()
    expect(modo.value).toBe('aviso')
    expect(p.abrirColmena).toHaveBeenCalledWith(null)
  })

  it('alternar abre y cierra el panel', () => {
    alternarPanel()
    expect(modo.value).toBe('panel')
    alternarPanel()
    expect(modo.value).toBe('cerrado')
  })

  it('abrirNotas pasa a modo notas y cerrarNotas vuelve a cerrado', () => {
    modo.value = 'cerrado'
    abrirNotas()
    expect(modo.value).toBe('notas')
    cerrarNotas()
    expect(modo.value).toBe('cerrado')
  })

  it('cerrarNotas no toca otro modo', () => {
    modo.value = 'panel'
    cerrarNotas()
    expect(modo.value).toBe('panel')
    modo.value = 'cerrado'
  })

  it('tocar la cara con notas abierta la cierra en vez de abrir el panel', () => {
    abrirNotas()
    alternarPanel()
    expect(modo.value).toBe('cerrado')
  })
})
