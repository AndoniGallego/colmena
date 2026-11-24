// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { observarFueraDeVista } from './fueraDeVista'

type Cb = (entries: Array<{ target: Element; isIntersecting: boolean }>) => void
let cb: Cb
const observe = vi.fn()
const unobserve = vi.fn()

function instalar() {
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      constructor(fn: Cb) {
        cb = fn
      }
      observe = observe
      unobserve = unobserve
    },
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  observe.mockClear()
  unobserve.mockClear()
})

describe('observarFueraDeVista', () => {
  it('marca data-fuera cuando el elemento sale de la vista y lo saca al volver', () => {
    instalar()
    const el = document.createElement('div')
    const soltar = observarFueraDeVista(el)
    expect(observe).toHaveBeenCalledWith(el)
    cb([{ target: el, isIntersecting: false }])
    expect(el.hasAttribute('data-fuera')).toBe(true)
    cb([{ target: el, isIntersecting: true }])
    expect(el.hasAttribute('data-fuera')).toBe(false)
    soltar()
    expect(unobserve).toHaveBeenCalledWith(el)
  })

  it('sin IntersectionObserver no hace nada', () => {
    vi.stubGlobal('IntersectionObserver', undefined)
    const el = document.createElement('div')
    expect(() => observarFueraDeVista(el)()).not.toThrow()
    expect(el.hasAttribute('data-fuera')).toBe(false)
  })
})
