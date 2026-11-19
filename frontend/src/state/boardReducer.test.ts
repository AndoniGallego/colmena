import { describe, expect, it } from 'vitest'
import type { AgentStatus, Board } from '../api/types'
import { boardReducer, initialBoardState, summarize, type BoardState } from './boardReducer'

function agent(pane: string, status: AgentStatus = 'idle', extra: object = {}) {
  return {
    pane_id: pane,
    kind: 'claude',
    status,
    session_id: `s-${pane}`,
    title: pane,
    doing: '',
    pending: '',
    asks_user: false,
    last_activity: null,
    ...extra,
  }
}

function board(at: string, statuses: Record<string, AgentStatus>, extra: Partial<Board> = {}): Board {
  return {
    updated_at: at,
    focused_tab_id: 'w1:t1',
    self_pane_id: null,
    workspaces: [
      {
        id: 'w1',
        number: 1,
        label: 'Uno',
        status: 'idle',
        tabs: [
          { id: 'w1:t1', label: '1', agents: [agent('w1:p1', statuses['w1:p1'])] },
          { id: 'w1:t2', label: '2', agents: [agent('w1:p2', statuses['w1:p2'])] },
        ],
      },
    ],
    terminales: 'ok',
    conflictos: [],
    caidos: [],
    ...extra,
  }
}

const T0 = '2026-10-30T10:00:00Z'
const T1 = '2026-10-30T10:00:05Z'

const withBoard = (b: Board): BoardState => boardReducer(initialBoardState(), { type: 'board', board: b })

describe('boardReducer', () => {
  it('stores the first board without transitions', () => {
    const s = withBoard(board(T0, { 'w1:p1': 'working' }))
    expect(s.board?.workspaces).toHaveLength(1)
    expect(s.transitions).toEqual({})
  })

  it('records status transitions with the previous status', () => {
    const s0 = withBoard(board(T0, { 'w1:p1': 'working', 'w1:p2': 'idle' }))
    const s1 = boardReducer(s0, { type: 'board', board: board(T1, { 'w1:p1': 'done', 'w1:p2': 'idle' }) })
    expect(s1.transitions).toEqual({ 'w1:p1': 'working' })
  })

  it('ignores boards older than the current one', () => {
    const s0 = withBoard(board(T1, { 'w1:p1': 'done' }))
    const s1 = boardReducer(s0, { type: 'board', board: board(T0, { 'w1:p1': 'working' }) })
    expect(s1).toBe(s0)
  })

  it('accepts boards with the same or unparseable timestamp', () => {
    const s0 = withBoard(board(T0, { 'w1:p1': 'idle' }))
    const s1 = boardReducer(s0, { type: 'board', board: board(T0, { 'w1:p1': 'working' }) })
    expect(s1.board?.workspaces[0].tabs[0].agents[0].status).toBe('working')
    const s2 = boardReducer(s1, { type: 'board', board: board('???', { 'w1:p1': 'done' }) })
    expect(s2.board?.workspaces[0].tabs[0].agents[0].status).toBe('done')
  })

  it('removes the orchestrator own pane, and tabs/workspaces left empty by it', () => {
    const b = board(T0, {}, { self_pane_id: 'w1:p2' })
    const s = withBoard(b)
    expect(s.board?.workspaces[0].tabs.map((t) => t.id)).toEqual(['w1:t1'])
    const only = withBoard({ ...b, self_pane_id: 'w1:p1', workspaces: [{ ...b.workspaces[0], tabs: [b.workspaces[0].tabs[0]] }] })
    expect(only.board?.workspaces).toEqual([])
  })

  it('keeps agent-less tabs that never held the orchestrator', () => {
    const b = board(T0, {}, { self_pane_id: 'zz:p9' })
    b.workspaces[0].tabs.push({ id: 'w1:t3', label: 'shell', agents: [] })
    expect(withBoard(b).board?.workspaces[0].tabs).toHaveLength(3)
  })

  it('applies focus optimistically and keeps it until the server confirms', () => {
    const s0 = withBoard(board(T0, {}))
    const s1 = boardReducer(s0, { type: 'focus/request', tabId: 'w1:t2' })
    expect(s1.board?.focused_tab_id).toBe('w1:t2')
    const stale = boardReducer(s1, { type: 'board', board: board(T1, {}) })
    expect(stale.board?.focused_tab_id).toBe('w1:t2')
    expect(stale.pendingFocus).toBe('w1:t2')
    const ok = boardReducer(stale, { type: 'board', board: board(T1, {}, { focused_tab_id: 'w1:t2' }) })
    expect(ok.pendingFocus).toBeNull()
    expect(ok.board?.focused_tab_id).toBe('w1:t2')
  })

  it('reverts focus when the request fails', () => {
    const s0 = withBoard(board(T0, {}))
    const s1 = boardReducer(s0, { type: 'focus/request', tabId: 'w1:t2' })
    const s2 = boardReducer(s1, { type: 'focus/request', tabId: 'w1:t1' })
    const s3 = boardReducer(s2, { type: 'focus/failed' })
    expect(s3.board?.focused_tab_id).toBe('w1:t1')
    expect(s3.pendingFocus).toBeNull()
  })

  it('ignores focus before the first board', () => {
    const s = initialBoardState()
    expect(boardReducer(s, { type: 'focus/request', tabId: 'x' })).toBe(s)
    expect(boardReducer(s, { type: 'focus/failed' })).toBe(s)
  })

  it('tracks connection state without churn', () => {
    const s0 = initialBoardState()
    const s1 = boardReducer(s0, { type: 'connection', state: 'live' })
    expect(s1.connection).toBe('live')
    expect(boardReducer(s1, { type: 'connection', state: 'live' })).toBe(s1)
  })

  it('clears transitions', () => {
    const s0 = withBoard(board(T0, { 'w1:p1': 'working' }))
    const s1 = boardReducer(s0, { type: 'board', board: board(T1, { 'w1:p1': 'done' }) })
    expect(boardReducer(s1, { type: 'transitions/clear' }).transitions).toEqual({})
    expect(boardReducer(s0, { type: 'transitions/clear' })).toBe(s0)
  })
})

describe('summarize · pendiente', () => {
  it('una pregunta pendiente no suma a asks ni a needs', () => {
    const b = board(T0, { 'w1:p1': 'idle', 'w1:p2': 'idle' })
    Object.assign(b.workspaces[0].tabs[0].agents[0], { asks_user: false, pendiente: true })
    expect(summarize(b)).toMatchObject({ asks: 0, needs: 0 })
  })
})

describe('summarize', () => {
  it('counts working, blocked and agents asking the user', () => {
    const b = board(T0, { 'w1:p1': 'working', 'w1:p2': 'blocked' })
    b.workspaces[0].tabs[1].agents[0].asks_user = true
    expect(summarize(b)).toEqual({ working: 1, blocked: 1, asks: 1, needs: 1, unread: 0, total: 2 })
    expect(summarize(null)).toEqual({ working: 0, blocked: 0, asks: 0, needs: 0, unread: 0, total: 0 })
  })
})

describe('boardReducer: reutiliza lo que no cambió', () => {
  const twoWs = (at: string, doing: string): Board => {
    const b = board(at, {})
    return {
      ...b,
      workspaces: [
        b.workspaces[0],
        { ...b.workspaces[0], id: 'w2', number: 2, label: 'Dos', tabs: [{ id: 'w2:t1', label: '1', agents: [agent('w2:p1', 'idle', { doing })] }] },
      ],
    }
  }
  const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x))

  it('con un solo agente distinto, los workspaces iguales conservan su identidad', () => {
    const s0 = withBoard(twoWs(T0, 'a'))
    const s1 = boardReducer(s0, { type: 'board', board: clone(twoWs(T1, 'b')) })
    expect(s1.board!.workspaces[0]).toBe(s0.board!.workspaces[0])
    expect(s1.board!.workspaces[1]).not.toBe(s0.board!.workspaces[1])
    expect(s1.board!.workspaces[1].tabs[0].agents[0].doing).toBe('b')
  })

  it('un tablero idéntico conserva los mismos workspaces', () => {
    const s0 = withBoard(twoWs(T0, 'a'))
    const s1 = boardReducer(s0, { type: 'board', board: clone(twoWs(T1, 'a')) })
    expect(s1.board!.workspaces).toBe(s0.board!.workspaces)
    expect(s1.board!.updated_at).toBe(T1)
  })

  it('el foco pendiente sigue mandando sobre focused_tab_id', () => {
    const s0 = withBoard(twoWs(T0, 'a'))
    const s1 = boardReducer(s0, { type: 'focus/request', tabId: 'w2:t1' })
    const s2 = boardReducer(s1, { type: 'board', board: clone(twoWs(T1, 'a')) })
    expect(s2.board!.focused_tab_id).toBe('w2:t1')
    expect(s2.board!.workspaces).toBe(s0.board!.workspaces)
  })
})

