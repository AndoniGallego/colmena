// @vitest-environment jsdom
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

type St = { y: number; yPercent: number; entering: boolean }
const state = new Map<HTMLElement, St>()
const st = (el: HTMLElement): St => {
  if (!state.has(el)) state.set(el, { y: 0, yPercent: 0, entering: false })
  return state.get(el)!
}
const render = (el: HTMLElement) => {
  const s = st(el)
  el.style.transform = [s.yPercent ? `translateY(${s.yPercent}%)` : '', s.y ? `translateY(${s.y}px)` : ''].filter(Boolean).join(' ')
}
const assign = (el: HTMLElement, v: { y?: number; yPercent?: number }) => {
  if (v.y !== undefined) st(el).y = v.y
  if (v.yPercent !== undefined) st(el).yPercent = v.yPercent
  render(el)
}
/** Entrada a medias de una hoja (yPercent 100 -> 0): si alguien la mata, queda donde estaba. */
function entrar(el: HTMLElement, at: number) {
  Object.assign(st(el), { yPercent: at, entering: true })
  render(el)
}
function terminarEntrada(el: HTMLElement) {
  if (st(el).entering) assign(el, { yPercent: 0 })
  st(el).entering = false
}
const gsapTo = vi.fn((el: HTMLElement, v: { y?: number; onComplete?: () => void }) => {
  assign(el, v)
  v.onComplete?.()
  return { kill: vi.fn() }
})
vi.mock('../motion', () => ({
  gsap: {
    set: (el: HTMLElement, v: { y?: number; yPercent?: number }) => assign(el, v),
    to: (el: HTMLElement, v: { y?: number; onComplete?: () => void }) => gsapTo(el, v),
    quickSetter: (el: HTMLElement, prop: 'y') => (val: number) => assign(el, { [prop]: val }),
    killTweensOf: (el: HTMLElement) => {
      st(el).entering = false
    },
    isTweening: () => false,
  },
  isSoft: () => false,
}))

const { useSheetSwipe } = await import('./useSheetSwipe')

function setup(onCloseImpl?: (panel: HTMLElement) => void, opts?: { direccion?: 'abajo' | 'arriba'; activo?: () => boolean }) {
  let panelRef: HTMLElement | null = null
  const onClose = vi.fn(() => onCloseImpl?.(panelRef!))
  const Comp = defineComponent({
    setup() {
      const panel = ref<HTMLElement | null>(null)
      useSheetSwipe(panel, onClose, opts)
      return () => h('section', { ref: panel }, [h('i', { class: 'sheet-grip' }), h('button', { class: 'dentro' }), h('p', { class: 'cuerpo' })])
    },
  })
  const w = mount(Comp, { attachTo: document.body })
  const panel = w.element as HTMLElement
  panelRef = panel
  Object.defineProperty(panel, 'offsetHeight', { value: 400 })
  return { w, panel, onClose, grip: panel.querySelector('.sheet-grip') as HTMLElement }
}

function ptr(type: string, target: Element, y: number, t: number, id = 1) {
  const e = new Event(type, { bubbles: true }) as Event & Record<string, unknown>
  Object.assign(e, { pointerId: id, clientY: y, clientX: 0, pointerType: 'touch', isPrimary: true })
  Object.defineProperty(e, 'timeStamp', { value: t })
  target.dispatchEvent(e)
}

describe('useSheetSwipe', () => {
  it('arrastrar más del 25% del alto desde la barrita cierra', async () => {
    const { grip, onClose, w } = setup()
    await nextTick()
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 60, 400)
    ptr('pointermove', grip, 120, 800)
    ptr('pointerup', grip, 120, 1200)
    expect(onClose).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('un tirón corto y lento vuelve y no cierra', async () => {
    const { grip, onClose, panel, w } = setup()
    await nextTick()
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 40, 800)
    expect(panel.style.transform).toBe('translateY(40px)')
    ptr('pointerup', grip, 40, 1600)
    expect(onClose).not.toHaveBeenCalled()
    expect(panel.style.transform).toBe('')
    w.unmount()
  })

  it('un flick rápido cierra aunque recorra poco', async () => {
    const { grip, onClose, w } = setup()
    await nextTick()
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 30, 20)
    ptr('pointermove', grip, 70, 60)
    ptr('pointerup', grip, 70, 70)
    expect(onClose).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('hacia arriba no cierra y hay resistencia', async () => {
    const { grip, onClose, panel, w } = setup()
    await nextTick()
    ptr('pointerdown', grip, 300, 0)
    ptr('pointermove', grip, 0, 50)
    expect(parseFloat(panel.style.transform.replace('translateY(', ''))).toBeGreaterThan(-60)
    ptr('pointerup', grip, 0, 100)
    expect(onClose).not.toHaveBeenCalled()
    w.unmount()
  })

  it('no arranca desde un botón ni desde el cuerpo', async () => {
    const { panel, onClose, w } = setup()
    await nextTick()
    for (const sel of ['.dentro', '.cuerpo']) {
      const t = panel.querySelector(sel) as Element
      ptr('pointerdown', t, 0, 0)
      ptr('pointermove', t, 300, 50)
      ptr('pointerup', t, 300, 100)
    }
    expect(onClose).not.toHaveBeenCalled()
    expect(panel.style.transform).toBe('')
    w.unmount()
  })

  it('agarrar la hoja mientras entra no la deja corrida: la entrada termina y el arrastre va por GSAP', async () => {
    const { grip, onClose, panel, w } = setup()
    await nextTick()
    entrar(panel, 6)
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 40, 800)
    expect(st(panel).y).toBe(40)
    ptr('pointerup', grip, 40, 1600)
    terminarEntrada(panel)
    expect(onClose).not.toHaveBeenCalled()
    expect(st(panel).yPercent).toBe(0)
    expect(st(panel).y).toBe(0)
    w.unmount()
  })

  it('un flick que se frena antes de soltar no cierra', async () => {
    const { grip, onClose, w } = setup()
    await nextTick()
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 30, 20)
    ptr('pointermove', grip, 70, 60)
    ptr('pointerup', grip, 70, 500)
    expect(onClose).not.toHaveBeenCalled()
    w.unmount()
  })

  it('si la hoja se va con una transición CSS sigue bajando en vez de volver', async () => {
    const { grip, onClose, panel, w } = setup((p) => p.parentElement!.classList.add('sheet-leave-active'))
    await nextTick()
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 60, 400)
    ptr('pointermove', grip, 120, 800)
    ptr('pointerup', grip, 120, 1200)
    expect(onClose).toHaveBeenCalledTimes(1)
    await nextTick()
    expect(st(panel).y).toBe(400)
    w.unmount()
  })
})

describe('useSheetSwipe direccion arriba (opt-in)', () => {
  it('arrastrar hacia arriba cierra y el panel sigue al dedo hacia arriba', async () => {
    const { grip, onClose, panel, w } = setup(undefined, { direccion: 'arriba' })
    await nextTick()
    ptr('pointerdown', grip, 300, 0)
    ptr('pointermove', grip, 240, 400)
    expect(panel.style.transform).toBe('translateY(-60px)')
    ptr('pointermove', grip, 180, 800)
    ptr('pointerup', grip, 180, 1200)
    expect(onClose).toHaveBeenCalledTimes(1)
    w.unmount()
  })

  it('arrastrar hacia abajo no cierra', async () => {
    const { grip, onClose, w } = setup(undefined, { direccion: 'arriba' })
    await nextTick()
    ptr('pointerdown', grip, 0, 0)
    ptr('pointermove', grip, 120, 400)
    ptr('pointerup', grip, 120, 800)
    expect(onClose).not.toHaveBeenCalled()
    w.unmount()
  })

  it('con activo() en falso no arranca', async () => {
    const { grip, onClose, panel, w } = setup(undefined, { direccion: 'arriba', activo: () => false })
    await nextTick()
    ptr('pointerdown', grip, 300, 0)
    ptr('pointermove', grip, 100, 400)
    ptr('pointerup', grip, 100, 800)
    expect(onClose).not.toHaveBeenCalled()
    expect(panel.style.transform).toBe('')
    w.unmount()
  })
})
