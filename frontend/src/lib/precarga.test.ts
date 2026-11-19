import { describe, expect, it, vi } from 'vitest'
import { precargarChat } from './precarga'

describe('precargarChat con deep link', () => {
  it('pide el chunk del chat en el acto, sin esperar el idle', () => {
    const cargar = vi.fn(() => Promise.resolve())
    precargarChat(() => {}, '?session=abc-123', cargar)
    expect(cargar).toHaveBeenCalledTimes(1)
  })
  it('sin deep link no adelanta nada', () => {
    const cargar = vi.fn(() => Promise.resolve())
    precargarChat(() => {}, '', cargar)
    expect(cargar).not.toHaveBeenCalled()
  })
})

describe('precargarChat', () => {
  it('no carga nada hasta que el navegador queda libre y luego dispara ambos imports', async () => {
    let cb: (() => void) | null = null
    precargarChat((f) => {
      cb = f
    })
    expect(cb).not.toBeNull()
    expect(() => cb!()).not.toThrow()
  })

  it('sin requestIdleCallback cae a setTimeout', () => {
    vi.useFakeTimers()
    const g = globalThis as { requestIdleCallback?: unknown }
    const prev = g.requestIdleCallback
    g.requestIdleCallback = undefined
    const spy = vi.spyOn(globalThis, 'setTimeout')
    precargarChat()
    expect(spy).toHaveBeenCalled()
    g.requestIdleCallback = prev
    spy.mockRestore()
    vi.useRealTimers()
  })
})
