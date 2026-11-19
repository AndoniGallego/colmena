import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'

let pop: () => void = () => {}
const entries: unknown[] = [null]
let at = 0
const fakeHistory = {
  get state() {
    return entries[at]
  },
  pushState(s: unknown) {
    entries.splice(++at, entries.length, s)
  },
  back() {
    at--
    pop()
  },
}

let mod: typeof import('./ajustes')

beforeAll(async () => {
  vi.stubGlobal('history', fakeHistory)
  vi.stubGlobal('window', { addEventListener: (_: string, fn: () => void) => (pop = fn), matchMedia: () => ({ matches: false, addEventListener: () => {} }) })
  mod = await import('./ajustes')
})
beforeEach(() => {
  mod.ajustesOpen.value = false
  entries.splice(0, entries.length, null)
  at = 0
})

describe('vista de Ajustes', () => {
  it('abrir suma una entrada de historial y el botón volver la saca', () => {
    mod.openAjustes()
    expect(mod.ajustesOpen.value).toBe(true)
    expect(at).toBe(1)
    mod.closeAjustes()
    expect(mod.ajustesOpen.value).toBe(false)
    expect(at).toBe(0)
  })

  it('el gesto atrás del navegador la cierra', () => {
    mod.openAjustes()
    fakeHistory.back()
    expect(mod.ajustesOpen.value).toBe(false)
  })

})
