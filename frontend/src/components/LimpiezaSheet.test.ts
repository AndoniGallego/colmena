// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../motion', () => ({
  gsap: { fromTo: vi.fn(), to: vi.fn(), set: vi.fn(), killTweensOf: vi.fn(), quickSetter: () => vi.fn(), isTweening: () => false, timeline: vi.fn() },
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

window.matchMedia = ((q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })) as unknown as typeof window.matchMedia

const { lm } = await import('../state/limpieza')
const { default: LimpiezaSheet } = await import('./LimpiezaSheet.vue')

function ptr(type: string, target: Element, y: number, t: number) {
  const e = new Event(type, { bubbles: true }) as Event & Record<string, unknown>
  Object.assign(e, { pointerId: 1, clientY: y, clientX: 0, pointerType: 'touch' })
  Object.defineProperty(e, 'timeStamp', { value: t })
  target.dispatchEvent(e)
}

describe('LimpiezaSheet arrastrar para cerrar', () => {
  it('arrastrar la barrita hacia abajo cierra la hoja', async () => {
    lm.open = true
    const w = mount(LimpiezaSheet, { attachTo: document.body })
    await flushPromises()
    const panel = document.body.querySelector('.sheet-panel') as HTMLElement
    Object.defineProperty(panel, 'offsetHeight', { value: 400 })
    const grip = panel.querySelector('.sheet-grip') as Element
    expect(grip).toBeTruthy()
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 150, 300)
    ptr('pointerup', grip, 150, 600)
    expect(lm.open).toBe(false)
    w.unmount()
  })
})
