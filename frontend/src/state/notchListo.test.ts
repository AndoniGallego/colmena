// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./app', async () => {
  const { shallowRef } = await import('vue')
  return { boardState: shallowRef({ connection: 'live' }) }
})

vi.mock('../lib/viewport', async () => {
  const { ref } = await import('vue')
  return { desktop: ref(false) }
})

type Tauri =NonNullable<Window['__TAURI__']>

describe('iniciarEscuchaNotas', () => {
  beforeEach(() => {
    vi.resetModules()
  })
  afterEach(() => {
    delete (window as { __TAURI__?: unknown }).__TAURI__
  })

  it('notch-listo se emite recién después de registrar notas-abrir y guia-abrir', async () => {
    const orden: string[] = []
    const registros: Record<string, () => void> = {}
    const listen = vi.fn((nombre: string) => {
      orden.push(`listen:${nombre}`)
      return new Promise<unknown>((r) => {
        registros[nombre] = () => r(() => undefined)
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
    expect(Object.keys(registros).sort()).toEqual(['guia-abrir', 'guia-listo', 'guia-siguiente', 'notas-abrir', 'nudo-salir'])
    registros['notas-abrir']()
    await new Promise((r) => setTimeout(r, 0))
    expect(emit).not.toHaveBeenCalled()
    registros['guia-abrir']()
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith('notch-listo'))
    expect(orden.at(-1)).toBe('emit')
    expect(emit).toHaveBeenCalledTimes(1)
  })

  it('con guia-abrir registrada primero también espera a notas-abrir', async () => {
    const registros: Record<string, () => void> = {}
    const listen = vi.fn((nombre: string) => new Promise<unknown>((r) => {
      registros[nombre] = () => r(() => undefined)
    }))
    const emit = vi.fn(() => Promise.resolve())
    ;(window as { __TAURI__?: Tauri }).__TAURI__ = { event: { listen, emit } }
    const { iniciarEscuchaNotas } = await import('./notch')
    iniciarEscuchaNotas()
    registros['guia-abrir']()
    await new Promise((r) => setTimeout(r, 0))
    expect(emit).not.toHaveBeenCalled()
    registros['notas-abrir']()
    await vi.waitFor(() => expect(emit).toHaveBeenCalledWith('notch-listo'))
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
