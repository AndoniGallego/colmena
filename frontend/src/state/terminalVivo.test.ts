import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../motion', () => ({
  gsap: {},
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('./terminalActions', () => ({
  tconfig: { value: { vivo: true } },
  loadTerminalConfig: vi.fn(),
}))

const { abrirVivo, consumirPedirPinAlAbrir, vivoAbierto } = await import('./terminalVivo')

beforeEach(() => {
  vivoAbierto.value = null
})

describe('abrirVivo pedirPin', () => {
  it('deja el flag cuando pedirPin es true', () => {
    abrirVivo('g1:p1', 'T', { pedirPin: true })
    expect(consumirPedirPinAlAbrir()).toBe(true)
    expect(consumirPedirPinAlAbrir()).toBe(false)
  })

  it('no deja flag por defecto', () => {
    abrirVivo('g1:p1', 'T')
    expect(consumirPedirPinAlAbrir()).toBe(false)
  })

  it('ignora terminales ajenas', () => {
    abrirVivo('otro:p1', 'T', { pedirPin: true })
    expect(vivoAbierto.value).toBeNull()
    expect(consumirPedirPinAlAbrir()).toBe(false)
  })
})
