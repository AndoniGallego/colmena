// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../motion', () => ({
  gsap: { fromTo: vi.fn(), to: vi.fn(), set: vi.fn(), killTweensOf: vi.fn(), quickSetter: () => vi.fn(), isTweening: () => false },
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: TerminalPinSheet } = await import('./TerminalPinSheet.vue')

function ptr(type: string, target: Element, y: number, t: number) {
  const e = new Event(type, { bubbles: true }) as Event & Record<string, unknown>
  Object.assign(e, { pointerId: 1, clientY: y, clientX: 0, pointerType: 'touch' })
  Object.defineProperty(e, 'timeStamp', { value: t })
  target.dispatchEvent(e)
}

describe('TerminalPinSheet arrastrar para cerrar', () => {
  it('arrastrar la barrita hacia abajo emite close', async () => {
    const w = mount(TerminalPinSheet, {
      props: { open: true, busy: false, error: null, lockedUntil: null },
      attachTo: document.body,
    })
    await flushPromises()
    const panel = document.body.querySelector('.sheet-panel') as HTMLElement
    Object.defineProperty(panel, 'offsetHeight', { value: 400 })
    const grip = panel.querySelector('.sheet-grip') as Element
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 150, 300)
    ptr('pointerup', grip, 150, 600)
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })
})
