import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type Api } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
})

const { boardState, init } = await import('./app')
const {
  chat,
  clearPendingStashForTests,
  discardPending,
  openSessionChat,
  openSessionId,
  refrescarConSeguimiento,
  releaseQueued,
  retryPending,
  sendFromSession,
} = await import('./session')

const setup = (fn: unknown) => init({ executeMensaje: fn } as Api)
const flush = async () => {
  for (let i = 0; i < 30; i++) await Promise.resolve()
}

beforeEach(() => {
  chat.pending = []
  chat.head = { title: '', status: 'idle', paneId: 'w1:p1' }
})

describe('sendFromSession', () => {
  it('cada mensaje tiene su burbuja e id, y salen en orden sin esperar al agente', async () => {
    const releases: Array<(v: unknown) => void> = []
    const fn = vi.fn().mockImplementation(() => new Promise((r) => releases.push(r)))
    setup(fn)
    const a = sendFromSession('w1:p1', 'S (w1:p1)', ' uno ', [])
    const b = sendFromSession('w1:p1', 'S (w1:p1)', 'dos', [])
    const c = sendFromSession('w1:p1', 'S (w1:p1)', 'tres', [])
    expect(chat.pending.map((p) => p.text)).toEqual(['uno', 'dos', 'tres'])
    expect(new Set([a.id, b.id, c.id]).size).toBe(3)
    await flush()
    expect(fn).toHaveBeenCalledTimes(1)
    releases[0]({ ok: true })
    await flush()
    releases[1]({ ok: true })
    await flush()
    releases[2]({ ok: true })
    await flush()
    expect(fn.mock.calls.map((c) => c[0].texto)).toEqual(['uno', 'dos', 'tres'])
    expect(chat.pending.map((p) => p.phase)).toEqual(['sent', 'sent', 'sent'])
  })

  it('marca en cola solo lo que se manda con la sesión trabajando', async () => {
    setup(vi.fn().mockResolvedValue({ ok: true }))
    expect(sendFromSession('w1:p1', 'x', 'libre', []).queued).toBe(false)
    chat.head.status = 'working'
    expect(sendFromSession('w1:p1', 'x', 'espera', []).queued).toBe(true)
    await flush()
  })

  it('un error deja la burbuja fallida y el reintento reusa el id; no frena a los demás', async () => {
    const fn = vi.fn().mockRejectedValueOnce(new ApiError(502, 'herdr falló')).mockResolvedValue({ ok: true })
    setup(fn)
    const a = sendFromSession('w1:p1', 'x', 'uno', [])
    const b = sendFromSession('w1:p1', 'x', 'dos', [])
    await flush()
    expect(a).toMatchObject({ phase: 'failed', error: 'herdr falló', queued: false })
    expect(b.phase).toBe('sent')
    retryPending(a)
    await flush()
    expect(a.phase).toBe('sent')
    expect(fn.mock.calls[2][0].id).toBe(fn.mock.calls[0][0].id)
    discardPending(b)
    expect(chat.pending).toEqual([a])
  })
  it('el fin del turno libera el "En cola" aunque no haya arrancado otro turno', async () => {
    setup(vi.fn().mockResolvedValue({ ok: true }))
    chat.head.status = 'working'
    await flush()
    const a = sendFromSession('w1:p1', 'x', 'espera', [])
    await flush()
    releaseQueued('working', 'working')
    releaseQueued('blocked', 'idle')
    expect(a.queued).toBe(true)
    releaseQueued('idle', 'working')
    expect(a.queued).toBe(false)
  })
})

describe('refrescarConSeguimiento', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('llama refreshTail ahora y otra vez a los 1500 ms', () => {
    const refresh = vi.fn()
    refrescarConSeguimiento(refresh, () => 'sid-1')
    expect(refresh).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(1500)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('dos llamadas seguidas no dejan dos seguimientos', () => {
    const refresh = vi.fn()
    refrescarConSeguimiento(refresh, () => 'sid-1')
    refrescarConSeguimiento(refresh, () => 'sid-1')
    expect(refresh).toHaveBeenCalledTimes(2)
    vi.advanceTimersByTime(1500)
    expect(refresh).toHaveBeenCalledTimes(3)
  })

  it('sin sesión activa no llama', () => {
    const refresh = vi.fn()
    refrescarConSeguimiento(refresh, () => null)
    vi.advanceTimersByTime(1500)
    expect(refresh).not.toHaveBeenCalled()
  })

  it('al vencer no refresca si cambió la sesión activa', () => {
    const refresh = vi.fn()
    let active = 'sid-a'
    refrescarConSeguimiento(refresh, () => active)
    active = 'sid-b'
    vi.advanceTimersByTime(1500)
    expect(refresh).toHaveBeenCalledTimes(1)
  })
})

describe('pendientes al cambiar de conversación', () => {
  const sidA = '11111111-aaaa-bbbb-cccc-dddddddddddd'
  const sidB = '22222222-bbbb-cccc-dddd-eeeeeeeeeeee'
  const pageA = { items: [], before: null, status_line: null, title: 'Sesión A', status: 'working' as 'working' | 'idle', pane_id: 'w1:p1' }
  const pageB = { items: [], before: null, status_line: null, title: 'Sesión B', status: 'idle' as const, pane_id: 'w1:p2' }

  const boardDos = (statusA: 'working' | 'idle') => ({
    workspaces: [
      {
        id: 'w1',
        number: 1,
        label: 'x',
        status: 'idle' as const,
        tabs: [
          {
            id: 'w1:t1',
            label: '',
            agents: [{ session_id: sidA, pane_id: 'w1:p1', status: statusA }],
          },
          {
            id: 'w1:t2',
            label: '',
            agents: [{ session_id: sidB, pane_id: 'w1:p2', status: 'idle' as const }],
          },
        ],
      },
    ],
  })

  beforeEach(() => {
    clearPendingStashForTests()
    vi.stubGlobal('history', { pushState() {}, replaceState() {}, back() {} })
    openSessionId.value = null
    init({
      executeMensaje: vi.fn().mockResolvedValue(undefined),
      getTranscript: vi.fn().mockImplementation(async (id: string) => (id === sidA ? pageA : pageB)),
    } as unknown as Api)
    boardState.value = {
      ...boardState.value,
      board: boardDos('working') as never,
      connection: 'live',
    }
  })

  it('(a) en A encolado → B → A: sigue en pending con queued si A sigue working', async () => {
    openSessionChat(sidA)
    await flush()
    const entry = sendFromSession('w1:p1', 'S (w1:p1)', 'espera', [])
    await flush()
    expect(entry).toMatchObject({ phase: 'sent', queued: true })
    openSessionChat(sidB)
    expect(chat.pending).toEqual([])
    openSessionChat(sidA)
    await flush()
    expect(chat.pending).toEqual([entry])
    expect(entry.queued).toBe(true)
  })

  it('(b) al volver a A ya idle, queued pasa a false', async () => {
    openSessionChat(sidA)
    await flush()
    const entry = sendFromSession('w1:p1', 'S (w1:p1)', 'espera', [])
    await flush()
    expect(entry.queued).toBe(true)
    openSessionChat(sidB)
    boardState.value = {
      ...boardState.value,
      board: boardDos('idle') as never,
    }
    openSessionChat(sidA)
    await flush()
    expect(chat.pending).toEqual([entry])
    expect(entry.queued).toBe(false)
  })

  it('(c) en B no aparecen los pendientes de A', async () => {
    openSessionChat(sidA)
    await flush()
    sendFromSession('w1:p1', 'S (w1:p1)', 'solo A', [])
    await flush()
    openSessionChat(sidB)
    await flush()
    expect(chat.pending.map((p) => p.text)).toEqual([])
  })

  it('(d) sin discard el pendiente guardado vuelve al reabrir A', async () => {
    openSessionChat(sidA)
    await flush()
    const entry = sendFromSession('w1:p1', 'S (w1:p1)', 'vuelve', [])
    await flush()
    openSessionChat(sidB)
    openSessionChat(sidA)
    await flush()
    expect(chat.pending).toEqual([entry])
  })

  it('(d) discardPending de uno guardado lo saca del mapa', async () => {
    openSessionChat(sidA)
    await flush()
    const entry = sendFromSession('w1:p1', 'S (w1:p1)', 'borrar', [])
    await flush()
    openSessionChat(sidB)
    discardPending(entry)
    openSessionChat(sidA)
    await flush()
    expect(chat.pending).toEqual([])
  })

  it('refresh de B no descarta un sent guardado de A por idx/texto del transcript de B', async () => {
    const pageAConHistorial = {
      ...pageA,
      items: [{ kind: 'user' as const, text: 'inicio A' }],
    }
    const pageBAlto = {
      ...pageB,
      before: 5,
      items: [{ kind: 'user' as const, text: 'colisiona test pendiente A reflejado en B' }],
    }
    init({
      executeMensaje: vi.fn().mockResolvedValue({ ok: true }),
      getTranscript: vi.fn().mockImplementation(async (id: string) => (id === sidA ? pageAConHistorial : pageBAlto)),
    } as unknown as Api)
    openSessionChat(sidA)
    await flush()
    const entry = sendFromSession('w1:p1', 'S (w1:p1)', 'colisiona test pendiente A', [])
    await flush()
    expect(entry).toMatchObject({ phase: 'sent', baseIdx: 0 })
    openSessionChat(sidB)
    await flush()
    openSessionChat(sidA)
    await flush()
    expect(chat.pending).toEqual([entry])
  })

  it('(d) expiración con la sesión en otra conversación saca del mapa', async () => {
    vi.useFakeTimers()
    pageA.status = 'idle'
    boardState.value = { ...boardState.value, board: boardDos('idle') as never }
    openSessionChat(sidA)
    await flush()
    sendFromSession('w1:p1', 'S (w1:p1)', 'caduca', [])
    await flush()
    openSessionChat(sidB)
    vi.advanceTimersByTime(90_000)
    openSessionChat(sidA)
    await flush()
    expect(chat.pending).toEqual([])
    vi.useRealTimers()
    pageA.status = 'working'
  })
})

describe('sesión que todavía no aparece', () => {
  it('reintenta sola cuando el tablero la muestra, sin quedar en "sin rastro"', async () => {
    const sid = '99999999-aaaa-bbbb-cccc-dddddddddddd'
    const page = { items: [], before: null, status_line: null, title: '', status: 'idle', pane_id: 'w9:p1' }
    let visible = false
    const getTranscript = vi.fn().mockImplementation(async () => {
      if (!visible) throw new ApiError(404, 'sesión no encontrada')
      return page
    })
    init({ getTranscript } as unknown as Api)
    vi.stubGlobal('history', { pushState() {}, replaceState() {}, back() {} })
    openSessionChat(sid)
    await flush()
    expect(chat.missing).toBe(true)
    const antes = getTranscript.mock.calls.length
    visible = true
    const agent = { session_id: sid, pane_id: 'w9:p1', status: 'idle' }
    boardState.value = {
      ...boardState.value,
      board: { workspaces: [{ id: 'w9', number: 9, label: 'x', status: 'idle', tabs: [{ id: 'w9:t1', label: '', agents: [agent] }] }] },
    } as never
    await flush()
    expect(getTranscript.mock.calls.length).toBeGreaterThan(antes)
    expect(chat.missing).toBe(false)
    expect(chat.loaded).toBe(true)
  })
})
