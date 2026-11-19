import { compartir } from '../lib/compartir'
import type { AgentStatus, Board, ConnectionState } from '../api/types'

export interface BoardState {
  board: Board | null
  connection: ConnectionState
  /** pane_id -> previous status, for agents whose status changed in the last update */
  transitions: Record<string, AgentStatus>
  /** tab id set optimistically while POST /api/focus is in flight */
  pendingFocus: string | null
  previousFocus: string | null
}

export type BoardAction =
  | { type: 'board'; board: Board }
  | { type: 'connection'; state: ConnectionState }
  | { type: 'focus/request'; tabId: string }
  | { type: 'focus/failed' }
  | { type: 'transitions/clear' }

export const initialBoardState = (): BoardState => ({
  board: null,
  connection: 'connecting',
  transitions: {},
  pendingFocus: null,
  previousFocus: null,
})

function statusByPane(board: Board | null): Map<string, AgentStatus> {
  const m = new Map<string, AgentStatus>()
  for (const w of board?.workspaces ?? []) for (const t of w.tabs) for (const a of t.agents) m.set(a.pane_id, a.status)
  return m
}

function stripSelf(board: Board): Board {
  if (!board.self_pane_id) return board
  const self = board.self_pane_id
  const hasSelf = (t: Board['workspaces'][number]['tabs'][number]) => t.agents.some((a) => a.pane_id === self)
  return {
    ...board,
    workspaces: board.workspaces.flatMap((w) => {
      if (!w.tabs.some(hasSelf)) return [w]
      const tabs = w.tabs.flatMap((t) => {
        if (!hasSelf(t)) return [t]
        const agents = t.agents.filter((a) => a.pane_id !== self)
        return agents.length ? [{ ...t, agents }] : []
      })
      return tabs.length ? [{ ...w, tabs }] : []
    }),
  }
}

const time = (iso: string | undefined) => {
  const t = iso ? Date.parse(iso) : NaN
  return Number.isNaN(t) ? null : t
}

export function boardReducer(state: BoardState, action: BoardAction): BoardState {
  switch (action.type) {
    case 'board': {
      const prevT = time(state.board?.updated_at)
      const nextT = time(action.board.updated_at)
      if (prevT !== null && nextT !== null && nextT < prevT) return state

      const next = state.board ? compartir(state.board, stripSelf(action.board)) : stripSelf(action.board)
      const before = statusByPane(state.board)
      const transitions: Record<string, AgentStatus> = {}
      if (state.board) {
        for (const [pane, status] of statusByPane(next)) {
          const prev = before.get(pane)
          if (prev !== undefined && prev !== status) transitions[pane] = prev
        }
      }
      const confirmed = state.pendingFocus !== null && next.focused_tab_id === state.pendingFocus
      const board =
        state.pendingFocus && !confirmed ? { ...next, focused_tab_id: state.pendingFocus } : next
      return {
        ...state,
        board,
        transitions,
        pendingFocus: confirmed ? null : state.pendingFocus,
        previousFocus: confirmed ? null : state.previousFocus,
      }
    }
    case 'connection':
      return state.connection === action.state ? state : { ...state, connection: action.state }
    case 'focus/request':
      if (!state.board) return state
      return {
        ...state,
        pendingFocus: action.tabId,
        previousFocus: state.pendingFocus ? state.previousFocus : state.board.focused_tab_id,
        board: { ...state.board, focused_tab_id: action.tabId },
      }
    case 'focus/failed':
      if (!state.board || state.pendingFocus === null) return state
      return {
        ...state,
        board: { ...state.board, focused_tab_id: state.previousFocus },
        pendingFocus: null,
        previousFocus: null,
      }
    case 'transitions/clear':
      return Object.keys(state.transitions).length ? { ...state, transitions: {} } : state
  }
}

export interface BoardSummary {
  working: number
  blocked: number
  asks: number
  /** sesiones distintas que esperan al usuario (bloqueadas, que preguntan o con respuesta nueva) */
  needs: number
  /** sesiones con una respuesta que todavía no viste */
  unread: number
  total: number
}

export function summarize(board: Board | null): BoardSummary {
  const s = { working: 0, blocked: 0, asks: 0, needs: 0, unread: 0, total: 0 }
  for (const w of board?.workspaces ?? [])
    for (const t of w.tabs)
      for (const a of t.agents) {
        s.total++
        if (a.status === 'working') s.working++
        if (a.status === 'blocked') s.blocked++
        if (a.asks_user) s.asks++
        if (a.unread) s.unread++
        if (a.status === 'blocked' || a.asks_user || a.unread) s.needs++
      }
  return s
}
