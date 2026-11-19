// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./app', async () => {
  const { shallowRef } = await import('vue')
  return { boardState: shallowRef({ connection: 'live' }) }
})

type Tauri = NonNullable<Window['__TAURI__']>

describe('iniciarEscuchaNotas', () => {
  beforeEach(() => {
    vi.resetModules()
  })
  afterEach(() => {
    delete (window as { __TAURI__?: unknown }).__TAURI__
  })

  it('avisa notch-listo recién después de registrar la escucha', async () => {
    const orden: string[] = []
    let registrada!: () => void
    const listen = vi.fn(() => {
      orden.push('listen')
      return new Promise<unknown>((r) => {
        registrada = () => r(() => undefined)
      })
    })
    const emit = vi.fn(() => {
      orden.push('emit')
      return Promise.resolve()
    })
    ;(window as { __TAURI__?: Tauri }).__TAURI__ = { event: { listen, emit } }
    const { iniciarEscuchaNotas } = await import('./notch')
    iniciarEscuchaNotas()
    await Promise.resolve()
    expect(emit).not.toHaveBeenCalled()
    registrada()
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith('notch-listo'))
    expect(orden).toEqual(['listen', 'emit'])
  })

  it('fuera de Windows no rompe ni avisa', async () => {
    const { iniciarEscuchaNotas } = await import('./notch')
    expect(() => iniciarEscuchaNotas()).not.toThrow()
  })

  it('si la escucha falla no avisa listo', async () => {
    const emit = vi.fn(() => Promise.resolve())
    const listen = vi.fn(() => Promise.reject(new Error('no')))
    ;(window as { __TAURI__?: Tauri }).__TAURI__ = { event: { listen, emit } }
    const { iniciarEscuchaNotas } = await import('./notch')
    iniciarEscuchaNotas()
    await new Promise((r) => setTimeout(r, 0))
    expect(emit).not.toHaveBeenCalled()
  })
})
