import { describe, expect, it } from 'vitest'
import type { TranscriptItem, TranscriptPage } from '../api/types'
import { findSession, groupThread, indexPage, mergeTail, parseDeepLink, parseDialogFlag, prependOlder, sentArrived, shortPath, toolLine, type ThreadState } from './transcript'

const it_ = (kind: TranscriptItem['kind'], text = '', name = '', summary = ''): TranscriptItem => ({ kind, text, name, summary, ts: '' })
const page = (items: TranscriptItem[], before: number | null): TranscriptPage => ({ items, before, title: 't', status: 'idle', pane_id: 'w1:p1', status_line: { model: '', ticket: '', ctx_pct: null, ctx_level: 'unknown', vpn: null } })
const texts = (s: ThreadState) => s.items.map((i) => `${i.idx}:${i.text}`)

describe('indexPage', () => {
  it('numbers items from the cursor', () => {
    expect(indexPage(page([it_('user', 'a'), it_('claude', 'b')], 10)).map((i) => i.idx)).toEqual([10, 11])
  })
  it('starts at zero when there is nothing older', () => {
    expect(indexPage(page([it_('user', 'a')], null))[0].idx).toBe(0)
  })
})

describe('mergeTail con un hueco en el servidor', () => {
  const at = (idx: number): TranscriptItem => ({ ...it_('claude', `m${idx}`), idx })
  it('no duplica cuando un ítem fue descartado antes de la cola', () => {
    const full = { items: indexPage(page([0, 1, 2, 4, 5, 6].map(at), null)), before: null }
    const next = mergeTail(full, page([5, 6, 7].map(at), 5))
    expect(texts(next)).toEqual(['0:m0', '1:m1', '2:m2', '4:m4', '5:m5', '6:m6', '7:m7'])
  })
  it('sin idx cae al cálculo por cursor', () => {
    expect(indexPage(page([it_('user', 'a')], 10))[0].idx).toBe(10)
  })
})

describe('mergeTail', () => {
  const first = { items: indexPage(page([it_('user', 'a'), it_('claude', 'b'), it_('user', 'c')], null)), before: null }

  it('appends only what is new', () => {
    const next = mergeTail(first, page([it_('claude', 'b'), it_('user', 'c'), it_('claude', 'd')], 1))
    expect(texts(next)).toEqual(['0:a', '1:b', '2:c', '3:d'])
  })
  it('does not duplicate when nothing changed', () => {
    const next = mergeTail(first, page([it_('user', 'a'), it_('claude', 'b'), it_('user', 'c')], null))
    expect(texts(next)).toEqual(['0:a', '1:b', '2:c'])
  })
  it('keeps older pages already loaded', () => {
    const loaded = prependOlder({ items: indexPage(page([it_('user', 'x'), it_('user', 'y')], 5)), before: 5 }, page([it_('user', 'w')], 4))
    const next = mergeTail(loaded, page([it_('user', 'y'), it_('user', 'z')], 6))
    expect(texts(next)).toEqual(['4:w', '5:x', '6:y', '7:z'])
    expect(next.before).toBe(4)
  })
  it('restarts from the page when it left a gap', () => {
    const next = mergeTail(first, page([it_('user', 'far')], 50))
    expect(texts(next)).toEqual(['50:far'])
    expect(next.before).toBe(50)
  })
  it('restarts when the transcript shrank', () => {
    const next = mergeTail(first, page([it_('user', 'a2')], null))
    expect(texts(next)).toEqual(['0:a2'])
  })
  it('ignores an empty page', () => {
    expect(mergeTail(first, page([], null))).toBe(first)
  })
  it('reutiliza la misma referencia si el ítem no cambió', () => {
    const ref = first.items[1]
    const next = mergeTail(first, page([it_('user', 'a'), it_('claude', 'b'), it_('user', 'c')], null))
    expect(next.items[1]).toBe(ref)
  })
  it('devuelve objeto nuevo si cambia el texto', () => {
    const ref = first.items[0]
    const next = mergeTail(first, page([it_('user', 'a2'), it_('claude', 'b'), it_('user', 'c')], null))
    expect(next.items[0]).not.toBe(ref)
    expect(next.items[0].text).toBe('a2')
  })
})

describe('prependOlder', () => {
  it('puts older items first and moves the cursor', () => {
    const state = { items: indexPage(page([it_('user', 'c')], 2)), before: 2 }
    const next = prependOlder(state, page([it_('user', 'a'), it_('claude', 'b')], null))
    expect(texts(next)).toEqual(['0:a', '1:b', '2:c'])
    expect(next.before).toBeNull()
  })
  it('drops items it already had', () => {
    const state = { items: indexPage(page([it_('user', 'b'), it_('user', 'c')], 1)), before: 1 }
    expect(texts(prependOlder(state, page([it_('user', 'a'), it_('user', 'b')], null)))).toEqual(['0:a', '1:b', '2:c'])
  })
})

describe('groupThread', () => {
  it('groups consecutive tools between messages', () => {
    const items = indexPage(page([it_('user', 'q'), it_('tool', '', 'Read', 'a'), it_('tool', '', 'Bash', 'b'), it_('claude', 'r'), it_('tool', '', 'Grep', 'c')], null))
    const g = groupThread(items)
    expect(g.map((e) => e.type)).toEqual(['msg', 'tools', 'msg', 'tools'])
    expect(g[1].type === 'tools' && g[1].tools.length).toBe(2)
  })
  it('keys are stable as the thread grows', () => {
    const base = indexPage(page([it_('user', 'q'), it_('tool', '', 'Read', 'a')], null))
    const grown = indexPage(page([it_('user', 'q'), it_('tool', '', 'Read', 'a'), it_('tool', '', 'Bash', 'b')], null))
    expect(groupThread(grown).map((e) => e.key)).toEqual(groupThread(base).map((e) => e.key))
  })
})

describe('toolLine', () => {
  it('shortens paths for file tools', () => {
    expect(toolLine('Read', '/home/usuario/proyectos/acme/ps9/modules/x/File.php')).toMatchObject({ verb: 'Leyó', target: '…/modules/x/File.php' })
  })
  it('keeps commands whole', () => {
    expect(toolLine('Bash', 'git status --short')).toMatchObject({ verb: 'Corrió', target: 'git status --short' })
  })
  it('names unknown and mcp tools', () => {
    expect(toolLine('Weird', 'x').verb).toBe('Usó Weird')
    expect(toolLine('mcp__claude_ai_Slack__slack_send_message', 'x').verb).toBe('Usó slack send message')
  })
})

describe('shortPath', () => {
  it('leaves short paths alone', () => {
    expect(shortPath('src/a.ts')).toBe('src/a.ts')
  })
})

describe('sentArrived', () => {
  const items = indexPage(page([it_('user', 'viejo'), it_('claude', 'ok'), it_('user', 'hacé el  deploy\nahora (Adjunto: /x/uploads/a.png)')], null))
  it('matches the text after the server flattens it', () => {
    expect(sentArrived(items, { text: 'hacé el deploy ahora', baseIdx: 1 })).toBe(true)
  })
  it('ignores messages from before the send', () => {
    expect(sentArrived(items, { text: 'viejo', baseIdx: 0 })).toBe(false)
  })
  it('matches attachment-only sends by their wording', () => {
    const only = indexPage(page([it_('user', 'Te paso /x/uploads/20261031-101500-a.png')], null))
    expect(sentArrived(only, { text: '', baseIdx: -1 })).toBe(true)
  })
})

describe('parseDeepLink', () => {
  it('reads the session id', () => {
    expect(parseDeepLink('?session=abc-123_X')).toBe('abc-123_X')
    expect(parseDeepLink('?mock=1&session=abc')).toBe('abc')
  })
  it('rejects anything that is not an id', () => {
    expect(parseDeepLink('')).toBeNull()
    expect(parseDeepLink('?session=')).toBeNull()
    expect(parseDeepLink('?session=../etc')).toBeNull()
    expect(parseDeepLink(`?session=${'a'.repeat(81)}`)).toBeNull()
  })
})

describe('parseDialogFlag', () => {
  it('needs the literal 1 and a valid session', () => {
    expect(parseDialogFlag('?session=abc&dialogo=1')).toBe(true)
    expect(parseDialogFlag('?dialogo=1&session=abc')).toBe(true)
    expect(parseDialogFlag('?session=abc&dialogo=true')).toBe(false)
    expect(parseDialogFlag('?session=abc&dialogo=2')).toBe(false)
    expect(parseDialogFlag('?session=abc')).toBe(false)
    expect(parseDialogFlag('?session=../x&dialogo=1')).toBe(false)
    expect(parseDialogFlag('?dialogo=1')).toBe(false)
  })
  it('keeps parseDeepLink reading the session', () => {
    expect(parseDeepLink('?session=abc&dialogo=1')).toBe('abc')
  })
})

describe('findSession', () => {
  const board = {
    updated_at: '',
    focused_tab_id: null,
    self_pane_id: null,
    workspaces: [{ id: 'w1', number: 1, label: 'W', status: 'idle', tabs: [{ id: 't1', label: '1', agents: [{ pane_id: 'p1', kind: 'claude', status: 'idle', session_id: 's1', title: '', doing: '', pending: '', asks_user: false, last_activity: null }] }] }],
  } as never
  it('finds the agent with its tab and workspace', () => {
    expect(findSession(board, 's1')?.tab.id).toBe('t1')
    expect(findSession(board, 'nope')).toBeNull()
    expect(findSession(null, 's1')).toBeNull()
  })
})

describe('groupThread con compactación', () => {
  it('deja el separador como mensaje y corta el grupo de tools', () => {
    const items = indexPage(page([it_('tool', '', 'Read', 'a'), it_('compact', 'resumen'), it_('tool', '', 'Read', 'b')], null))
    expect(groupThread(items).map((e) => e.type)).toEqual(['tools', 'msg', 'tools'])
  })
})
