import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Api, Subagente } from '../api/types'

const doc = vi.hoisted(() => {
  const listeners: Record<string, Array<() => void>> = {}
  const d = {
    visibilityState: 'visible',
    createElement: () => ({ style: {}, setAttribute() {}, classList: { add() {} } }),
    createElementNS: () => ({}),
    querySelector: () => null,
    addEventListener: (n: string, f: () => void) => (listeners[n] ??= []).push(f),
    removeEventListener: () => {},
    fire: (n: string) => (listeners[n] ?? []).forEach((f) => f()),
  }
  vi.stubGlobal('document', d)
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
  return d
})

const { init } = await import('./app')
const { POLL_MS, stopSubagentes, subagentes, watchSubagentes } = await import('./subagentes')

const mk = (estado: Subagente['estado']): Subagente => ({ id: 'a', descripcion: 'x', tipo: '', modelo: '', estado, inicio: '', segundos: 1, paso: '', tokens: null })

beforeEach(() => {
  vi.useFakeTimers()
  doc.visibilityState = 'visible'
})
afterEach(() => {
  stopSubagentes()
  vi.useRealTimers()
})

describe('sondeo de subagentes', () => {
  it('sondea cada 4 s mientras alguno trabaja y para al terminar', async () => {
    const fn = vi.fn().mockResolvedValueOnce([mk('trabajando')]).mockResolvedValueOnce([mk('trabajando')]).mockResolvedValue([mk('termino')])
    init({ getSubagentes: fn } as unknown as Api)
    watchSubagentes('s1', () => false)
    await vi.advanceTimersByTimeAsync(0)
    expect(fn).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await vi.advanceTimersByTimeAsync(POLL_MS)
    expect(fn).toHaveBeenCalledTimes(3)
    expect(subagentes.value[0].estado).toBe('termino')
    await vi.advanceTimersByTimeAsync(POLL_MS * 5)
    expect(fn).toHaveBeenCalledTimes(3)
  })

  it('no sondea con la app oculta y retoma al volver', async () => {
    const fn = vi.fn().mockResolvedValue([mk('trabajando')])
    init({ getSubagentes: fn } as unknown as Api)
    watchSubagentes('s1', () => false)
    await vi.advanceTimersByTimeAsync(0)
    doc.visibilityState = 'hidden'
    doc.fire('visibilitychange')
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(fn).toHaveBeenCalledTimes(1)
    doc.visibilityState = 'visible'
    doc.fire('visibilitychange')
    await vi.advanceTimersByTimeAsync(0)
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('sigue mirando si la sesión está trabajando aunque no haya agentes', async () => {
    const fn = vi.fn().mockResolvedValue([])
    init({ getSubagentes: fn } as unknown as Api)
    watchSubagentes('s1', () => true)
    await vi.advanceTimersByTimeAsync(POLL_MS * 2)
    expect(fn.mock.calls.length).toBeGreaterThanOrEqual(3)
  })
})
