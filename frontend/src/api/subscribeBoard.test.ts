import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createHttpApi } from './http'
import { EVENTO_CURSOR } from '../lib/tareas'

type Listener = (ev: MessageEvent) => void

class MockEventSource {
  static last: MockEventSource | null = null
  listeners: Record<string, Listener[]> = {}
  readyState = 1
  constructor(public url: string) {
    MockEventSource.last = this
    queueMicrotask(() => this.listeners.open?.forEach((fn) => fn(new MessageEvent('open'))))
  }
  addEventListener(type: string, fn: Listener) {
    ;(this.listeners[type] ??= []).push(fn)
  }
  close() {}
  emit(type: string, data: string) {
    const ev = { data } as MessageEvent
    this.listeners[type]?.forEach((fn) => fn(ev))
  }
}

describe('subscribeBoard centinela_aprueba', () => {
  beforeEach(() => {
    MockEventSource.last = null
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    vi.stubGlobal('document', {
      visibilityState: 'visible',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      hasFocus: () => true,
    })
    vi.stubGlobal('window', {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
    })
    vi.stubGlobal('crypto', { randomUUID: () => 'dev-1' })
  })

  afterEach(() => vi.unstubAllGlobals())

  describe('presencia', () => {
    const winHandlers: Record<string, (e: Event) => void> = {}
    const docHandlers: Record<string, (e: Event) => void> = {}

    beforeEach(() => {
      vi.stubGlobal('window', {
        addEventListener: vi.fn((t: string, fn: (e: Event) => void) => {
          winHandlers[t] = fn
        }),
        removeEventListener: vi.fn(),
        matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
      })
      vi.stubGlobal('document', {
        visibilityState: 'visible',
        addEventListener: vi.fn((t: string, fn: (e: Event) => void) => {
          docHandlers[t] = fn
        }),
        removeEventListener: vi.fn(),
        hasFocus: () => true,
      })
    })

    it('no reporta presencia por ningún evento', () => {
      const api = createHttpApi(() => {})
      const off = api.subscribeBoard({ onBoard: vi.fn(), onState: vi.fn() }, { presencia: false })
      const es = MockEventSource.last!
      es.emit('build', JSON.stringify({ id: 'b2' }))
      es.emit('ping', JSON.stringify({}))
      for (const t of ['focus', 'blur', 'pagehide']) winHandlers[t]?.(new Event(t))
      docHandlers.visibilitychange?.(new Event('visibilitychange'))
      expect(vi.mocked(fetch).mock.calls.filter(([u]) => u === '/api/presencia')).toEqual([])
      off()
    })

    it('por defecto sigue reportando presencia', () => {
      const api = createHttpApi(() => {})
      const off = api.subscribeBoard({ onBoard: vi.fn(), onState: vi.fn() })
      const es = MockEventSource.last!
      es.emit('build', JSON.stringify({ id: 'b2' }))
      const presencia = vi.mocked(fetch).mock.calls.filter(([u]) => u === '/api/presencia')
      expect(presencia.length).toBeGreaterThanOrEqual(1)
      const body = presencia[0]![1] as RequestInit
      expect(String(body.body)).toContain('"device":"dev-1"')
      off()
    })

    it('incluye escritorio en presencia cuando hay getter', () => {
      const api = createHttpApi(() => {})
      const off = api.subscribeBoard({ onBoard: vi.fn(), onState: vi.fn() }, { escritorio: () => true })
      const es = MockEventSource.last!
      es.emit('build', JSON.stringify({ id: 'b2' }))
      const presencia = vi.mocked(fetch).mock.calls.filter(([u]) => u === '/api/presencia')
      expect(String((presencia[0]![1] as RequestInit).body)).toContain('"escritorio":true')
      off()
    })
  })

  it('abrir_terminal invoca callback con pane_id y titulo', () => {
    const onAbrirTerminal = vi.fn()
    const api = createHttpApi(() => {})
    const off = api.subscribeBoard({ onBoard: vi.fn(), onState: vi.fn(), onAbrirTerminal })
    const es = MockEventSource.last!
    es.emit('abrir_terminal', JSON.stringify({ pane_id: 'g1:p2', titulo: 'Mi sesión' }))
    es.emit('abrir_terminal', JSON.stringify({ titulo: 'sin pane' }))
    expect(onAbrirTerminal).toHaveBeenCalledTimes(1)
    expect(onAbrirTerminal).toHaveBeenCalledWith({ pane_id: 'g1:p2', titulo: 'Mi sesión' })
    off()
  })

  it('el evento cursor avisa a la ventana para que se recarguen los trabajadores', () => {
    const dispatchEvent = vi.fn()
    vi.stubGlobal('window', {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent,
      matchMedia: () => ({ matches: false, addEventListener: vi.fn() }),
    })
    const api = createHttpApi(() => {})
    const off = api.subscribeBoard({ onBoard: vi.fn(), onState: vi.fn() })
    MockEventSource.last!.emit('cursor', JSON.stringify({ id: 'a'.repeat(32), estado: 'ok' }))
    expect(dispatchEvent).toHaveBeenCalledTimes(1)
    expect((dispatchEvent.mock.calls[0]![0] as Event).type).toBe(EVENTO_CURSOR)
    off()
  })
})
