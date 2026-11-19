import { describe, expect, it } from 'vitest'
import { debeAutofocoAlAbrir } from './autofocoChat'

const base = { desktop: true, punteroFino: true, editando: false }

describe('debeAutofocoAlAbrir', () => {
  it('autofoco en PC con mouse', () => {
    expect(debeAutofocoAlAbrir(base)).toBe(true)
  })
  it('no autofoco en celu, así no se abre el teclado', () => {
    expect(debeAutofocoAlAbrir({ ...base, desktop: false, punteroFino: false })).toBe(false)
  })
  it('no autofoco en pantallas anchas táctiles', () => {
    expect(debeAutofocoAlAbrir({ ...base, punteroFino: false })).toBe(false)
  })
  it('no le roba el foco a otro campo donde estás escribiendo', () => {
    expect(debeAutofocoAlAbrir({ ...base, editando: true })).toBe(false)
  })
})
