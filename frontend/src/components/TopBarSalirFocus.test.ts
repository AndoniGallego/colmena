// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.stubGlobal('window', {
  matchMedia: () => ({ matches: true, addEventListener() {}, removeEventListener() {} }),
  innerWidth: 1200,
  addEventListener() {},
  removeEventListener() {},
})

vi.mock('../motion', () => ({
  gsap: { from() {}, fromTo() {}, utils: { selector: () => () => [] } },
  isSoft: () => true,
  ring: () => {},
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../lib/viewport', () => ({ desktop: ref(true) }))
vi.mock('../state/app', () => ({
  boardState: ref({ connection: 'live', board: null }),
  jumpTo: vi.fn(),
  revokeAllSessions: vi.fn(async () => true),
}))
vi.mock('../state/biblioteca', () => ({ lib: { newCount: 0 }, libVisible: ref(false) }))
vi.mock('../piezas', () => ({ piezas: () => [] }))
vi.mock('../state/mrs', () => ({ mrs: { habilitado: false }, mrsVisible: ref(false), pendientesMrs: ref(false) }))
vi.mock('../state/limpieza', () => ({ abrirLimpieza: vi.fn() }))
vi.mock('../lib/theme', () => ({ theme: ref('light'), setTheme: vi.fn() }))
vi.mock('../state/ajustes', () => ({ openAjustes: vi.fn() }))
vi.mock('../state/entornos', () => ({ openEntornos: vi.fn() }))
vi.mock('../state/buscador', () => ({ abrirPaleta: vi.fn() }))
vi.mock('../lib/buscador', () => ({ ATAJO: '⌘K' }))
vi.mock('../lib/time', () => ({ useNow: () => ref(Date.now()), clock: (t: number) => String(t) }))
vi.mock('./BrandLockup.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./NavMark.vue', () => ({ default: { template: '<span />' } }))
vi.mock('./AvisosBell.vue', () => ({ default: { template: '<div class="bell" />' } }))
vi.mock('./RollingNumber.vue', () => ({ default: { template: '<span>0</span>' } }))
vi.mock('./SinConexion.vue', () => ({ default: { template: '<motion-span />' } }))

const { default: TopBar } = await import('./TopBar.vue')

describe('TopBar salir popover trampa de foco', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('Escape con el foco adentro cierra una sola vez', async () => {
    const w = mount(TopBar, { props: { compact: false }, attachTo: document.body })
    await flushPromises()
    const salir = w.find('[aria-label="Salir de Colmena"]').element as HTMLButtonElement
    salir.click()
    await flushPromises()
    const dialog = document.querySelector<HTMLElement>('[aria-label="Confirmar salida"]')
    expect(dialog).toBeTruthy()
    const danger = dialog!.querySelector<HTMLButtonElement>('.danger')!
    danger.focus()
    dialog!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.querySelector('[aria-label="Confirmar salida"]')).toBeNull()
    w.unmount()
  })

  it('Tab desde el último elemento vuelve al primero', async () => {
    const w = mount(TopBar, { props: { compact: false }, attachTo: document.body })
    await flushPromises()
    w.find('[aria-label="Salir de Colmena"]').element.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    const dialog = document.querySelector<HTMLElement>('[aria-label="Confirmar salida"]')!
    const buttons = [...dialog.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
    const first = buttons[0]
    const last = buttons[buttons.length - 1]
    last.focus()
    dialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(first)
    w.unmount()
  })
})
