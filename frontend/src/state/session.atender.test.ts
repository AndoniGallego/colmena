import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api } from '../api/types'
import * as aLaVista from '../lib/aLaVista'

const { markSeenMock } = vi.hoisted(() => ({ markSeenMock: vi.fn() }))

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: true, addEventListener() {} }),
    addEventListener: vi.fn(),
  })
  vi.stubGlobal('location', { search: '', pathname: '/' })
})

vi.mock('./app', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./app')>()
  return { ...actual, markSeen: markSeenMock }
})

const { boardState, init } = await import('./app')
const { desktop } = await import('../lib/viewport')
const { atenderSesion, openSessionChat, openSessionId, sesionAtendida } = await import('./session')

const sid = '11111111-aaaa-bbbb-cccc-dddddddddddd'
const page = { items: [], before: null, status_line: null, title: 'S', status: 'idle' as const, pane_id: 'w1:p1' }

const board = (agent: { unread?: boolean; status?: string }) => ({
  workspaces: [
    {
      id: 'w1',
      number: 1,
      label: 'x',
      status: 'idle' as const,
      tabs: [{ id: 'w1:t1', label: '', agents: [{ session_id: sid, pane_id: 'w1:p1', status: 'idle' as const, ...agent }] }],
    },
  ],
})

const flush = async () => {
  for (let i = 0; i < 20; i++) await Promise.resolve()
}

beforeEach(() => {
  markSeenMock.mockClear()
  sesionAtendida.value = null
  openSessionId.value = null
  desktop.value = true
  vi.spyOn(aLaVista, 'estaALaVista').mockReturnValue(true)
  vi.stubGlobal('history', { pushState() {}, replaceState() {}, back() {} })
  init({
    executeMensaje: vi.fn().mockResolvedValue(undefined),
    getTranscript: vi.fn().mockResolvedValue(page),
  } as unknown as Api)
  boardState.value = { ...boardState.value, board: board({ unread: false, status: 'idle' }) as never, connection: 'live' }
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('atender sesión', () => {
  it('abrir a la vista marca seen y emite sesionAtendida', async () => {
    boardState.value = { ...boardState.value, board: board({ unread: true, status: 'idle' }) as never }
    openSessionChat(sid)
    await flush()
    expect(markSeenMock).toHaveBeenCalledWith(sid)
    expect(sesionAtendida.value).toEqual({ id: sid, n: 1 })
  })

  it('sesión abierta que pasa a done sin interacción no llama markSeen', async () => {
    boardState.value = { ...boardState.value, board: board({ unread: false, status: 'idle' }) as never }
    openSessionChat(sid)
    await flush()
    markSeenMock.mockClear()
    sesionAtendida.value = null
    boardState.value = { ...boardState.value, board: board({ unread: false, status: 'done' }) as never }
    await flush()
    expect(markSeenMock).not.toHaveBeenCalled()
    expect(sesionAtendida.value).toBeNull()
  })

  it('atenderSesion sin estar a la vista no marca', async () => {
    openSessionId.value = sid
    boardState.value = { ...boardState.value, board: board({ unread: true, status: 'idle' }) as never }
    await flush()
    markSeenMock.mockClear()
    sesionAtendida.value = null
    vi.mocked(aLaVista.estaALaVista).mockReturnValue(false)
    atenderSesion()
    expect(markSeenMock).not.toHaveBeenCalled()
    expect(sesionAtendida.value).toBeNull()
  })

  it('atenderSesion a la vista con unread marca', async () => {
    openSessionId.value = sid
    boardState.value = { ...boardState.value, board: board({ unread: true, status: 'idle' }) as never }
    await flush()
    markSeenMock.mockClear()
    atenderSesion()
    expect(markSeenMock).toHaveBeenCalledWith(sid)
    expect(sesionAtendida.value?.id).toBe(sid)
  })
})
