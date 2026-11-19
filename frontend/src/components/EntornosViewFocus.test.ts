// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.stubGlobal('window', {
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  innerWidth: 800,
  addEventListener() {},
  removeEventListener() {},
  scrollTo() {},
  visualViewport: null,
})

vi.mock('../lib/viewport', () => ({ desktop: { value: true } }))
vi.mock('../lib/keyboard', () => ({ useKeyboard: () => ({ open: { value: false }, height: { value: null }, top: { value: 0 } }) }))
vi.mock('../motion', () => ({
  useGsap: () => ({ run: (fn: () => void) => fn() }),
  isSoft: () => true,
  animateViewEnter: vi.fn(),
  gsap: {},
}))

const closeEntornos = vi.fn()

vi.mock('../state/entornos', () => ({
  entornos: {
    enPrograma: true,
    notebook: '',
    lista: [],
    error: '',
    cargando: false,
    abriendo: [],
    cerrando: [],
    errores: {},
    tuneles: {},
  },
  closeEntornos: (...a: unknown[]) => closeEntornos(...a),
  cargarEntornos: vi.fn(),
  refrescarTuneles: vi.fn(),
  abrirEntorno: vi.fn(),
  abrirPuerto: vi.fn(),
  cerrarEntorno: vi.fn(),
  cambiarNotebook: vi.fn(),
}))

vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./ViewFrame.vue', () => ({
  default: defineComponent({
    name: 'ViewFrame',
    template: '<div class="vf-mock"><slot name="back" /><slot /></div>',
  }),
}))
vi.mock('./InlineAlert.vue', () => ({ default: { template: '<p><slot /></p>' } }))
vi.mock('./EntornosProbador.vue', () => ({
  default: { name: 'EntornosProbador', template: '<div class="en-probador-mock" />' },
}))

const { default: EntornosView } = await import('./EntornosView.vue')

describe('EntornosView trampa de foco', () => {
  afterEach(() => {
    closeEntornos.mockClear()
    document.body.innerHTML = ''
  })

  it('Escape con el foco adentro cierra una sola vez', async () => {
    const w = mount(EntornosView, { attachTo: document.body })
    await flushPromises()
    const panel = w.find('[aria-label="Entornos"]').element as HTMLElement
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(closeEntornos).toHaveBeenCalledOnce()
    w.unmount()
  })

  it('Tab desde el último elemento enfocable vuelve al primero', async () => {
    const w = mount(EntornosView, { attachTo: document.body })
    await flushPromises()
    const panel = w.find('[aria-label="Entornos"]').element as HTMLElement
    const focusable = [...panel.querySelectorAll<HTMLElement>('button:not(:disabled), [href], input:not(:disabled)')].filter(
      (el) => el.offsetParent !== null || el === document.activeElement,
    )
    if (focusable.length < 2) {
      panel.innerHTML += '<button type="button" id="t-extra">Extra</button>'
    }
    const buttons = [...panel.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
    expect(buttons.length).toBeGreaterThanOrEqual(1)
    const first = buttons[0]
    const last = buttons[buttons.length - 1]
    last.focus()
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement).toBe(first)
    w.unmount()
  })
})
