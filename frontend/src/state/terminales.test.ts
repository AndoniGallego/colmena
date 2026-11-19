import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type Api, type TerminalSalida } from '../api/types'

const doc = vi.hoisted(() => {
  const listeners: Record<string, Array<() => void>> = {}
  const d = {
    visibilityState: 'visible',
    createElement: () => ({ style: {}, setAttribute() {}, classList: { add() {} } }),
    createElementNS: () => ({}),
    querySelector: () => null,
    addEventListener: (n: string, f: () => void) => (listeners[n] ??= []).push(f),
    removeEventListener: (n: string, f: () => void) => (listeners[n] = (listeners[n] ?? []).filter((x) => x !== f)),
    fire: (n: string) => (listeners[n] ?? []).forEach((f) => f()),
  }
  vi.stubGlobal('document', d)
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
  return d
})

const { init } = await import('./app')
const { lines, poll, stopWatching, terminalFromUrl, view, watchTerminal, POLL_MS } = await import('./terminales')

const salida = (over: Partial<TerminalSalida> = {}): TerminalSalida => ({ sin_cambios: false, revision: 'r1', ansi: 'hola', truncado: false, cwd: '~', proceso: 'bash', estado: 'prompt', puede_escribir: true, motivo: null, ...over })
const tick = async (ms: number) => {
  await vi.advanceTimersByTimeAsync(ms)
}

beforeEach(() => {
  vi.useFakeTimers()
  doc.visibilityState = 'visible'
})
afterEach(() => {
  stopWatching()
  vi.useRealTimers()
})

describe('sondeo del visor', () => {
  it('sondea cada 1500 ms, manda la revisión y no reparsea sin cambios', async () => {
    const fn = vi.fn().mockResolvedValueOnce(salida()).mockResolvedValue(salida({ sin_cambios: true, ansi: '' }))
    init({ getTerminalSalida: fn } as unknown as Api)
    watchTerminal('w1:p5')
    await tick(0)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(lines.value).toHaveLength(1)
    const first = lines.value
    await tick(POLL_MS)
    expect(fn).toHaveBeenCalledTimes(2)
    expect(fn.mock.calls[1][1]).toBe('r1')
    expect(lines.value).toBe(first)
    await tick(POLL_MS * 3)
    expect(fn).toHaveBeenCalledTimes(5)
  })

  it('no sondea con la pestaña oculta y retoma al volver', async () => {
    const fn = vi.fn().mockResolvedValue(salida())
    init({ getTerminalSalida: fn } as unknown as Api)
    watchTerminal('w1:p5')
    await tick(0)
    doc.visibilityState = 'hidden'
    doc.fire('visibilitychange')
    await tick(POLL_MS * 10)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(view.paused).toBe(true)
    doc.visibilityState = 'visible'
    doc.fire('visibilitychange')
    await tick(0)
    expect(fn).toHaveBeenCalledTimes(2)
    expect(view.paused).toBe(false)
  })

  it('con errores espera 3, 6, 12 y tope 15 s', async () => {
    const fn = vi.fn().mockRejectedValue(new ApiError(502, 'Las terminales no respondieron'))
    init({ getTerminalSalida: fn } as unknown as Api)
    watchTerminal('w1:p5')
    await tick(0)
    expect(fn).toHaveBeenCalledTimes(1)
    expect(view.error).toBe('Las terminales no respondieron')
    await tick(2999)
    expect(fn).toHaveBeenCalledTimes(1)
    await tick(1)
    expect(fn).toHaveBeenCalledTimes(2)
    await tick(6000)
    expect(fn).toHaveBeenCalledTimes(3)
    await tick(12000)
    expect(fn).toHaveBeenCalledTimes(4)
    await tick(12000)
    expect(fn).toHaveBeenCalledTimes(5)
  })

  it('404 detiene el sondeo y marca la terminal como ausente', async () => {
    const fn = vi.fn().mockRejectedValue(new ApiError(404, 'la terminal ya no está'))
    init({ getTerminalSalida: fn } as unknown as Api)
    watchTerminal('w1:p5')
    await tick(0)
    expect(view.gone).toBeTruthy()
    await tick(POLL_MS * 10)
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('al cerrar aborta la lectura en vuelo y no deja timers', async () => {
    let signal: AbortSignal | null = null
    const fn = vi.fn().mockImplementation((_p: string, _r: string, s: AbortSignal) => {
      signal = s
      return new Promise(() => {})
    })
    init({ getTerminalSalida: fn } as unknown as Api)
    watchTerminal('w1:p5')
    await tick(0)
    stopWatching()
    expect(signal!.aborted).toBe(true)
    await tick(POLL_MS * 5)
    expect(fn).toHaveBeenCalledTimes(1)
    await poll()
    expect(fn).toHaveBeenCalledTimes(1)
  })
})

describe('enlace a una terminal', () => {
  it('solo acepta un id de pane válido', () => {
    expect(terminalFromUrl('?terminal=w1%3Ap5')).toBe('w1:p5')
    expect(terminalFromUrl('?terminal=-x')).toBeNull()
    expect(terminalFromUrl('?terminal=%3Cscript%3E')).toBeNull()
    expect(terminalFromUrl('?terminal=' + 'a'.repeat(65))).toBeNull()
    expect(terminalFromUrl('?chat=jefe')).toBeNull()
  })
})
