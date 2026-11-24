import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createHttpApi } from './http'

type Listener = (ev: MessageEvent) => void
class FakeES {
  static last: FakeES | null = null
  listeners: Record<string, Listener[]> = {}
  readyState = 1
  constructor(public url: string) {
    FakeES.last = this
  }
  addEventListener(t: string, fn: Listener) {
    ;(this.listeners[t] ??= []).push(fn)
  }
  close() {}
  emit(t: string, data: string) {
    this.listeners[t]?.forEach((fn) => fn({ data } as MessageEvent))
  }
}

describe('subscribeBoard nudo', () => {
  beforeEach(() => {
    FakeES.last = null
    vi.stubGlobal('EventSource', FakeES)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 200 })))
    vi.stubGlobal('document', { visibilityState: 'visible', addEventListener: vi.fn(), removeEventListener: vi.fn(), hasFocus: () => true })
    vi.stubGlobal('window', { addEventListener: vi.fn(), removeEventListener: vi.fn(), matchMedia: () => ({ matches: false, addEventListener: vi.fn() }) })
    vi.stubGlobal('crypto', { randomUUID: () => 'dev-1' })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('con pcNudo la URL lleva pc=1', () => {
    createHttpApi(() => {}).subscribeBoard({ onBoard: vi.fn(), onState: vi.fn() }, { presencia: false, pcNudo: true })()
    expect(FakeES.last!.url).toBe('/api/events?cid=dev-1&pc=1')
  })
  it('sin la opción no lleva pc', () => {
    createHttpApi(() => {}).subscribeBoard({ onBoard: vi.fn(), onState: vi.fn() }, { presencia: false })()
    expect(FakeES.last!.url).toBe('/api/events?cid=dev-1')
  })
  it('el evento nudo llama onNudo con los datos y el device', () => {
    const onNudo = vi.fn()
    createHttpApi(() => {}).subscribeBoard({ onBoard: vi.fn(), onState: vi.fn(), onNudo }, { presencia: false, pcNudo: true })()
    FakeES.last!.emit('nudo', JSON.stringify({ id: 'abcdefgh', op: 'estado' }))
    expect(onNudo).toHaveBeenCalledWith({ id: 'abcdefgh', op: 'estado' }, 'dev-1')
  })
  it('el evento guia llama onGuia con los datos y el device', () => {
    const onGuia = vi.fn()
    createHttpApi(() => {}).subscribeBoard({ onBoard: vi.fn(), onState: vi.fn(), onGuia }, { presencia: false, pcNudo: true })()
    FakeES.last!.emit('guia', JSON.stringify({ guia: 1, estado: 'mirando', paso: 0, total: 0, texto: '' }))
    expect(onGuia).toHaveBeenCalledWith({ guia: 1, estado: 'mirando', paso: 0, total: 0, texto: '' }, 'dev-1')
  })
})
