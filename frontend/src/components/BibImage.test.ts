// @vitest-environment jsdom
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../motion', () => ({
  gsap: { set: vi.fn(), to: vi.fn() },
  isSoft: () => true,
}))

const { default: BibImage } = await import('./BibImage.vue')

function ptr(type: string, target: Element, x: number, y: number, id: number) {
  const e = new Event(type, { bubbles: true }) as Event & Record<string, unknown>
  Object.assign(e, { pointerId: id, clientX: x, clientY: y, pointerType: 'touch' })
  target.dispatchEvent(e)
}

describe('BibImage punteros', () => {
  it('al perder la captura olvida el puntero y un dedo nuevo no hace zoom', async () => {
    const w = mount(BibImage, { props: { src: 'a.png', alt: 'a' }, attachTo: document.body })
    const zoom = w.element as HTMLElement
    zoom.setPointerCapture = vi.fn()
    ptr('pointerdown', zoom, 0, 0, 1)
    ptr('lostpointercapture', zoom, 0, 0, 1)
    ptr('pointerdown', zoom, 100, 100, 2)
    ptr('pointermove', zoom, 300, 100, 2)
    await nextTick()
    expect(zoom.classList.contains('zoomed')).toBe(false)
    w.unmount()
  })
})
