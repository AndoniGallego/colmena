import { describe, expect, it, vi } from 'vitest'
import type { Api } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
  vi.stubGlobal('history', { pushState() {}, replaceState() {}, back() {} })
})

const { boardState, init } = await import('./app')
const { closeSessionChat, openSessionChat, refreshTail, threadItems, REFRESCOS_PARCIALES } = await import('./session')

const flush = async () => {
  for (let i = 0; i < 30; i++) await Promise.resolve()
}
const SID = '11111111-aaaa-bbbb-cccc-dddddddddddd'
const mk = (from: number, n: number) => ({
  items: Array.from({ length: n }, (_, i) => ({ kind: 'user', text: `m${from + i}`, ts: 't' })),
  before: from > 0 ? from : null,
  status_line: null, title: 't', status: 'idle', pane_id: 'w1:p1',
})

function armar(total: { n: number }) {
  closeSessionChat()
  const getTranscript = vi.fn().mockImplementation(async (_id: string, _b: number | null, _l: number, desde?: number | null) => {
    if (desde == null || desde >= total.n) return mk(Math.max(0, total.n - 60), Math.min(60, total.n))
    const start = Math.max(0, desde - 5)
    return mk(start, total.n - start)
  })
  init({ getTranscript } as unknown as Api)
  return getTranscript
}

describe('cola incremental del transcript', () => {
  it('la primera carga es completa y los refrescos siguientes piden desde el ultimo idx', async () => {
    const total = { n: 20 }
    const get = armar(total)
    openSessionChat(SID)
    await flush()
    expect(get.mock.calls[0][3] ?? null).toBeNull()
    total.n = 23
    await refreshTail()
    expect(get.mock.calls[1][3]).toBe(19)
    expect(threadItems.value.map((i) => i.text)).toEqual(Array.from({ length: 23 }, (_, i) => `m${i}`))
  })

  it('al reconectar el SSE fuerza una pagina completa', async () => {
    const total = { n: 20 }
    const get = armar(total)
    boardState.value = { ...boardState.value, connection: 'live' } as never
    openSessionChat(SID)
    await flush()
    boardState.value = { ...boardState.value, connection: 'reconnecting' } as never
    await flush()
    const antes = get.mock.calls.length
    boardState.value = { ...boardState.value, connection: 'live' } as never
    await flush()
    expect(get.mock.calls.length).toBe(antes + 1)
    expect(get.mock.calls[antes][3] ?? null).toBeNull()
    await refreshTail()
    expect(get.mock.calls[antes + 1][3]).toBe(19)
  })

  it('cada cierto numero de refrescos parciales pide una pagina completa', async () => {
    const total = { n: 20 }
    const get = armar(total)
    openSessionChat(SID)
    await flush()
    for (let i = 0; i < REFRESCOS_PARCIALES; i++) await refreshTail()
    const parciales = get.mock.calls.slice(1).map((c) => c[3] ?? null)
    expect(parciales.slice(0, REFRESCOS_PARCIALES - 1).every((d) => d === 19)).toBe(true)
    expect(parciales[REFRESCOS_PARCIALES - 1]).toBeNull()
  })

  it('si el transcript se trunco, la pagina completa reemplaza lo que habia', async () => {
    const total = { n: 20 }
    armar(total)
    openSessionChat(SID)
    await flush()
    total.n = 8
    await refreshTail()
    expect(threadItems.value.map((i) => i.text)).toEqual(Array.from({ length: 8 }, (_, i) => `m${i}`))
  })
})
