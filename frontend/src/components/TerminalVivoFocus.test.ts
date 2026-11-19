// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { focusableIn } from '../lib/focusTrap'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const termMock = vi.hoisted(() => {
  class Terminal {
    open = vi.fn()
    write = vi.fn()
    reset = vi.fn()
    resize = vi.fn()
    dispose = vi.fn()
    onData = vi.fn(() => ({ dispose: vi.fn() }))
    options = { fontSize: 13, theme: {} as Record<string, string>, disableStdin: true }
    element = { querySelector: () => null }
  }
  return { Terminal }
})

vi.mock('@xterm/xterm', () => ({ Terminal: termMock.Terminal }))
vi.mock('@xterm/xterm/css/xterm.css', () => ({}))

vi.mock('../lib/vivo', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../lib/vivo')>()
  class ConexionVivoMock {
    abrir = vi.fn()
    cerrar = vi.fn()
    reintentar = vi.fn()
    despertar = vi.fn()
    constructor() {}
  }
  return { ...orig, ConexionVivo: ConexionVivoMock }
})

vi.mock('../motion', () => ({
  finePointer: () => false,
  haptic: () => {},
  isSoft: () => true,
  gsap: { set() {}, to() {}, from() {}, killTweensOf() {}, utils: { selector: () => () => [] } },
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../lib/viewport', () => ({ desktop: { value: true } }))
const writeState = vi.hoisted(() => ({
  ventanaAbierta: { value: true },
  ventana: { token: 'tok-test', venceAt: Date.now() + 3_600_000, idleAt: 0, inactividad: 600, now: Date.now() },
  countdown: { value: 600 },
}))
vi.mock('../state/terminalWrite', () => ({
  ventanaAbierta: writeState.ventanaAbierta,
  ventana: writeState.ventana,
  countdown: writeState.countdown,
  forgetVentana: vi.fn(),
  openVentana: vi.fn(),
  pinProblem: () => ({ message: 'x', retryAfter: null }),
  touchVentana: vi.fn(),
}))
vi.mock('../state/terminalActions', () => ({
  tconfig: { value: { escritura: true } },
}))
vi.mock('./Icon.vue', () => ({ default: { template: '<i />' } }))
vi.mock('./LogoLoader.vue', () => ({ default: { template: '<span />' } }))
vi.mock('./TerminalPinSheet.vue', () => ({ default: { template: '<div />' } }))

vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {} })
vi.stubGlobal('getComputedStyle', () => ({ display: 'block', getPropertyValue: () => '' }))
vi.stubGlobal('location', { protocol: 'http:', host: 'localhost' })
vi.stubGlobal('MutationObserver', class {
  observe() {}
  disconnect() {}
})
vi.stubGlobal('ResizeObserver', class {
  observe() {}
  disconnect() {}
})

const { vivoAbierto, cerrarVivo } = await import('../state/terminalVivo')
const { default: TerminalVivo } = await import('./TerminalVivo.vue')

describe('TerminalVivo trampa de foco', () => {
  beforeEach(() => {
    cerrarVivo()
    vivoAbierto.value = { paneId: 'p1', titulo: 'Test' } as typeof vivoAbierto.value
  })

  afterEach(() => {
    cerrarVivo()
    document.body.innerHTML = ''
  })

  it('Escape con el foco adentro cierra una sola vez', async () => {
    const w = mount(TerminalVivo, { attachTo: document.body })
    await flushPromises()
    const panel = w.find('.card').element as HTMLElement
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(vivoAbierto.value).toBeNull()
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(vivoAbierto.value).toBeNull()
    w.unmount()
  })

  it('Escape con escribiendo y foco adentro no cierra', async () => {
    const w = mount(TerminalVivo, { attachTo: document.body })
    await flushPromises()
    const teclado = w.find('.kbd-btn')
    expect(teclado.exists()).toBe(true)
    await teclado.trigger('click')
    await flushPromises()
    expect(w.find('.card').classes()).toContain('escribiendo')
    const panel = w.find('.card').element as HTMLElement
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(vivoAbierto.value).not.toBeNull()
    w.unmount()
  })

  it('Escape con escribiendo y foco afuera no cierra', async () => {
    const outer = document.createElement('button')
    document.body.appendChild(outer)
    outer.focus()
    const w = mount(TerminalVivo, { attachTo: document.body })
    await flushPromises()
    await w.find('.kbd-btn').trigger('click')
    await flushPromises()
    expect(document.activeElement).not.toBe(w.find('.card').element)
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(vivoAbierto.value).not.toBeNull()
    w.unmount()
    outer.remove()
  })

  it('Tab desde el último control vuelve al primero', async () => {
    const w = mount(TerminalVivo, { attachTo: document.body })
    await flushPromises()
    const panel = w.find('.card').element as HTMLElement
    const items = focusableIn(panel)
    const first = items[0]
    const last = items[items.length - 1]
    last.focus()
    expect(document.activeElement).toBe(last)
    last.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true }))
    expect(document.activeElement).toBe(first)
    w.unmount()
  })
})
