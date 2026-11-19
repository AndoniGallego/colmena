// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

const cerrarPaleta = vi.fn()

vi.mock('../motion', () => ({
  gsap: { set: vi.fn(), to: vi.fn(), from: vi.fn(), fromTo: vi.fn(), timeline: vi.fn(() => ({ fromTo: vi.fn(), from: vi.fn() })) },
  haptic: vi.fn(),
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../lib/keyboard', () => ({ useKeyboard: () => ({ open: ref(false), height: ref(0), top: ref(0) }) }))
vi.mock('../lib/viewport', () => ({ desktop: ref(true) }))
vi.mock('../lib/buscador', () => ({
  ATAJO: '⌘K',
  saltoDeGrupo: () => 0,
  tramos: () => [],
}))
vi.mock('../state/buscador', () => ({
  alternarPaleta: vi.fn(),
  cerrarPaleta: (...a: unknown[]) => cerrarPaleta(...a),
  elegir: vi.fn(),
  paleta: ref(true),
  planos: () => [],
  resultados: () => [],
}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: CommandPalette } = await import('./CommandPalette.vue')

describe('CommandPalette IME', () => {
  afterEach(() => {
    cerrarPaleta.mockClear()
  })

  it('Escape con isComposing no cierra la paleta', async () => {
    mount(CommandPalette, { attachTo: document.body })
    await flushPromises()
    const root = document.querySelector<HTMLElement>('.pal')
    expect(root).toBeTruthy()
    const ev = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    Object.defineProperty(ev, 'isComposing', { value: true })
    root!.dispatchEvent(ev)
    expect(cerrarPaleta).not.toHaveBeenCalled()
  })
})
