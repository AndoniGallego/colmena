import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

const pops: (() => void)[] = []
const entries: unknown[] = [null]
let at = 0
const fakeHistory = {
  get state() {
    return entries[at]
  },
  pushState(s: unknown) {
    entries.splice(++at, entries.length, s)
  },
  replaceState(s: unknown) {
    entries[at] = s
  },
  back() {
    if (at === 0) return
    at--
    pops.forEach((fn) => fn())
  },
}

let historyEntry: typeof import('./historyEntry').historyEntry

beforeAll(async () => {
  vi.stubGlobal('history', fakeHistory)
  vi.stubGlobal('window', { addEventListener: (_: string, fn: () => void) => pops.push(fn) })
  historyEntry = (await import('./historyEntry')).historyEntry
})
beforeEach(() => {
  entries.splice(0, entries.length, { otra: 1 })
  at = 0
})

describe('historyEntry', () => {
  it('abrir suma una entrada y volver (botón propio) la saca y cierra', () => {
    const onBack = vi.fn()
    const e = historyEntry('orqMr', onBack)
    e.push('1:2')
    expect(at).toBe(1)
    expect(fakeHistory.state).toEqual({ otra: 1, orqMr: '1:2' })
    expect(e.back()).toBe(true)
    expect(at).toBe(0)
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(e.pushed).toBe(false)
  })

  it('el Atrás del navegador o el gesto de volver cierran la vista', () => {
    const onBack = vi.fn()
    const e = historyEntry('orqMr', onBack)
    e.push('1:2')
    fakeHistory.back()
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(e.back()).toBe(false)
  })

  it('abrir otro detalle encima reemplaza la entrada en vez de apilar', () => {
    const e = historyEntry('orqMr', () => {})
    e.push('1:2')
    e.push('3:4')
    expect(at).toBe(1)
    expect(fakeHistory.state).toEqual({ otra: 1, orqMr: '3:4' })
  })

  it('sin entrada propia, volver no toca el historial', () => {
    const onBack = vi.fn()
    const e = historyEntry('orqMr', onBack)
    expect(e.back()).toBe(false)
    expect(at).toBe(0)
    expect(onBack).not.toHaveBeenCalled()
  })

  it('un popstate ajeno (otra vista) no la cierra', () => {
    const onBack = vi.fn()
    const e = historyEntry('orqMr', onBack)
    e.push('1:2')
    fakeHistory.pushState({ ...(fakeHistory.state as object), orqLib: 'x' })
    fakeHistory.back()
    expect(onBack).not.toHaveBeenCalled()
    expect(e.pushed).toBe(true)
  })
})
