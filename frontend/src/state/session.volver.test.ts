import { beforeEach, describe, expect, it, vi } from 'vitest'

const handlers = vi.hoisted(() => ({ popstate: null as null | ((e: unknown) => void) }))

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener: (type: string, fn: (e: unknown) => void) => {
      if (type === 'popstate') handlers.popstate = fn
    },
  })
  vi.stubGlobal('location', { search: '', pathname: '/' })
})

const { cierreSinTransicion, initSessionNav, openSessionId, terminarCierreSinTransicion } = await import('./session')

initSessionNav()

const popstate = (state: unknown, hasUAVisualTransition?: boolean) => {
  const e: Record<string, unknown> = { state }
  if (hasUAVisualTransition !== undefined) e.hasUAVisualTransition = hasUAVisualTransition
  handlers.popstate!(e)
}

beforeEach(() => {
  popstate({ orqSession: 's1' })
  terminarCierreSinTransicion()
})

describe('volver con el gesto del navegador', () => {
  it('cierra sin transicion cuando el navegador ya animo el gesto', () => {
    popstate(null, true)
    expect(openSessionId.value).toBeNull()
    expect(cierreSinTransicion.value).toBe(true)
  })

  it('se apaga al terminar el cierre', () => {
    popstate(null, true)
    terminarCierreSinTransicion()
    expect(cierreSinTransicion.value).toBe(false)
  })

  it('se apaga al abrir otra sesion', () => {
    popstate(null, true)
    popstate({ orqSession: 's2' }, false)
    expect(cierreSinTransicion.value).toBe(false)
  })

  it('con false o sin la propiedad el cierre anima como siempre', () => {
    popstate(null, false)
    expect(cierreSinTransicion.value).toBe(false)
    popstate({ orqSession: 's1' })
    popstate(null)
    expect(openSessionId.value).toBeNull()
    expect(cierreSinTransicion.value).toBe(false)
  })

  it('abrir con el gesto adelante no desactiva la animacion de entrada', () => {
    popstate({ orqSession: 's3' }, true)
    expect(cierreSinTransicion.value).toBe(false)
  })
})
