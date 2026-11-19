import type { Agent, Board, TranscriptItem, TranscriptPage, Tab, Workspace } from '../api/types'

export interface IndexedItem extends TranscriptItem {
  idx: number
}

export interface ThreadState {
  items: IndexedItem[]
  before: number | null
}

export type ThreadEntry =
  | { key: string; type: 'msg'; item: IndexedItem }
  | { key: string; type: 'tools'; tools: IndexedItem[] }

/** Each item carries its absolute position; without it (older server) it falls back to cursor + offset. */
export function indexPage(page: TranscriptPage): IndexedItem[] {
  const start = page.before ?? 0
  return page.items.map((item, i) => ({ ...item, idx: item.idx ?? start + i }))
}

function itemUnchanged(a: IndexedItem, b: IndexedItem): boolean {
  return (
    a.idx === b.idx &&
    a.text === b.text &&
    a.ts === b.ts &&
    a.kind === b.kind &&
    a.name === b.name &&
    a.summary === b.summary &&
    JSON.stringify(a.compact ?? null) === JSON.stringify(b.compact ?? null) &&
    JSON.stringify(a.lib_ids ?? null) === JSON.stringify(b.lib_ids ?? null) &&
    JSON.stringify(a.fotos ?? null) === JSON.stringify(b.fotos ?? null)
  )
}

export function mergeTail(state: ThreadState, page: TranscriptPage): ThreadState {
  const incoming = indexPage(page)
  if (!incoming.length) return state
  const last = state.items[state.items.length - 1]
  const tailEnd = incoming[incoming.length - 1].idx
  if (!last || tailEnd < last.idx || incoming[0].idx > last.idx + 1) return { items: incoming, before: page.before }
  const kept = state.items.filter((i) => i.idx < incoming[0].idx)
  const byIdx = new Map(state.items.map((i) => [i.idx, i]))
  const tail = incoming.map((item) => {
    const prev = byIdx.get(item.idx)
    return prev && itemUnchanged(prev, item) ? prev : item
  })
  return { items: [...kept, ...tail], before: kept.length ? state.before : page.before }
}

export function prependOlder(state: ThreadState, page: TranscriptPage): ThreadState {
  const first = state.items[0]?.idx ?? Infinity
  const older = indexPage(page).filter((i) => i.idx < first)
  return { items: [...older, ...state.items], before: page.before }
}

export function groupThread(items: IndexedItem[]): ThreadEntry[] {
  const out: ThreadEntry[] = []
  for (const item of items) {
    const prev = out[out.length - 1]
    if (item.kind !== 'tool') out.push({ key: `m${item.idx}`, type: 'msg', item })
    else if (prev?.type === 'tools') prev.tools.push(item)
    else out.push({ key: `t${item.idx}`, type: 'tools', tools: [item] })
  }
  return out
}

export function shortPath(path: string, keep = 3): string {
  const parts = path.split('/').filter(Boolean)
  return parts.length > keep + 1 ? `…/${parts.slice(-keep).join('/')}` : path
}

export type ToolIcon = 'doc' | 'terminal' | 'search' | 'pen' | 'dots'

const VERBS: Record<string, [string, ToolIcon, boolean]> = {
  read: ['Leyó', 'doc', true],
  bash: ['Corrió', 'terminal', false],
  grep: ['Buscó', 'search', false],
  glob: ['Listó', 'search', false],
  edit: ['Editó', 'pen', true],
  multiedit: ['Editó', 'pen', true],
  notebookedit: ['Editó', 'pen', true],
  write: ['Escribió', 'doc', true],
  webfetch: ['Abrió', 'search', false],
  websearch: ['Buscó en la web', 'search', false],
  task: ['Delegó', 'dots', false],
  agent: ['Delegó', 'dots', false],
  todowrite: ['Actualizó tareas', 'dots', false],
}

export function toolLine(name: string, summary: string): { verb: string; target: string; icon: ToolIcon } {
  const known = VERBS[name.toLowerCase()]
  if (known) return { verb: known[0], icon: known[1], target: known[2] ? shortPath(summary) : summary }
  const mcp = /^mcp__[^_]+(?:_[^_]+)*__(.+)$/.exec(name)
  return { verb: `Usó ${(mcp?.[1] ?? name).replace(/_/g, ' ')}`, icon: 'dots', target: summary }
}

export function findSession(board: Board | null, sessionId: string): { agent: Agent; ws: Workspace; tab: Tab } | null {
  for (const ws of board?.workspaces ?? [])
    for (const tab of ws.tabs) {
      const agent = tab.agents.find((a) => a.session_id === sessionId)
      if (agent) return { agent, ws, tab }
    }
  return null
}

export function findSessionByPane(board: Board | null, paneId: string): string | null {
  for (const ws of board?.workspaces ?? [])
    for (const tab of ws.tabs) {
      const agent = tab.agents.find((a) => a.pane_id === paneId)
      if (agent?.session_id) return agent.session_id
    }
  return null
}

const norm = (s: string) => s.replace(/\s+/g, ' ').trim()

/** The server flattens line breaks and may append attachment paths, so only the opening is compared. */
export function sentArrived(items: IndexedItem[], sent: { text: string; baseIdx: number }): boolean {
  const head = norm(sent.text || 'Te paso').slice(0, 80)
  return items.some((i) => {
    if (i.kind !== 'user' || i.idx <= sent.baseIdx) return false
    return norm(i.text).startsWith(head)
  })
}

const SESSION_PARAM = /^[A-Za-z0-9_-]{1,80}$/

export function parseDeepLink(search: string): string | null {
  const value = new URLSearchParams(search).get('session')
  return value && SESSION_PARAM.test(value) ? value : null
}

/** `dialogo=1` marks a push that points at a dialog; it only counts next to a valid session. */
export function parseDialogFlag(search: string): boolean {
  const params = new URLSearchParams(search)
  return parseDeepLink(search) !== null && params.get('dialogo') === '1'
}
