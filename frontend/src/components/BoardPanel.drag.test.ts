// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { Board, Workspace } from '../api/types'

const gsapMock = vi.hoisted(() => ({
  from: () => {},
  fromTo: () => {},
  to: vi.fn(),
  set: vi.fn(),
  killTweensOf: () => {},
  timeline: () => ({ fromTo: () => ({}), to: () => ({}) }),
}))
vi.mock('../motion', () => ({
  gsap: gsapMock,
  Flip: { getState: () => null, from: () => ({ progress: () => ({ kill: () => {} }) }) },
  isSoft: () => false,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
  vSpotlight: () => {},
  haptic: () => {},
}))
vi.mock('../lib/viewport', () => ({ desktop: { value: true } }))
vi.mock('../lib/time', () => ({ useNow: () => ref(Date.now()), ago: () => 'hace 1 min' }))
vi.mock('../state/mudanza', () => ({ iniciarMudanza: vi.fn() }))
vi.mock('../state/ordenTablero', () => ({
  ordenGuardado: ref([]),
  ordenError: ref(''),
  plegadasError: ref(''),
  plegadasGuardado: ref([]),
  hayOrdenManual: ref(false),
  guardarOrden: vi.fn(),
  guardarPlegadas: vi.fn(),
  volverOrdenAutomatico: vi.fn(),
}))
const boardRef = ref<Board | null>(null)
vi.mock('../state/app', () => ({
  boardState: { get value() { return { board: boardRef.value, connection: 'live', transitions: {} } } },
  highlight: { value: null },
}))
vi.mock('./WorkspaceCard.vue', () => ({
  default: {
    props: ['ws', 'now', 'reorder'],
    emits: ['reorder-move', 'reorder-key', 'grip-down', 'grip-cancel-hold', 'toggle-plegada'],
    render(this: { ws: Workspace; $emit: (e: string, ...a: unknown[]) => void }) {
      return h('div', { class: 'ws', onPointerdown: (e: Event) => this.$emit('grip-down', e) })
    },
  },
}))
for (const n of ['LimpiezaChip', 'MudanzaChip', 'MudanzaSheet', 'NuevaTerminalSheet', 'RetomarSesionSheet', 'Icon', 'EmptyState'])
  vi.doMock(`./${n}.vue`, () => ({ default: { render: () => null } }))
vi.mock('./ViewFrame.vue', () => ({
  default: { props: ['title'], render(this: { $slots: { default?: () => unknown } }) { return this.$slots.default?.() } },
}))

const { default: BoardPanel } = await import('./BoardPanel.vue')

const mk = (id: string, number: number): Workspace => ({
  id, number, label: id, pinned: false, status: 'idle', tabs: [{ id: `${id}:t1`, label: '1', agents: [] }],
})

function ptr(type: string, y: number): Event {
  const e = new Event(type, { bubbles: true, cancelable: true })
  Object.assign(e, { clientY: y, pointerId: 1, pointerType: 'mouse', button: 0 })
  return e
}

async function montar() {
  boardRef.value = {
    updated_at: new Date().toISOString(), focused_tab_id: null, self_pane_id: null,
    workspaces: [mk('w1', 1), mk('w2', 2), mk('w3', 3)], terminales: 'ok', conflictos: [], caidos: [],
  }
  const root = document.createElement('div')
  document.body.appendChild(root)
  createApp({ render: () => h(BoardPanel) }).mount(root)
  await nextTick()
  const cards = [...root.querySelectorAll<HTMLElement>('.ws')]
  const reads = vi.fn()
  cards.forEach((c, i) => {
    c.getBoundingClientRect = () => {
      reads()
      return { top: i * 100, height: 98, bottom: i * 100 + 98, left: 0, right: 0, width: 0, x: 0, y: i * 100, toJSON: () => ({}) }
    }
    c.setPointerCapture = () => {}
    c.hasPointerCapture = () => false
  })
  return { cards, reads, root }
}

describe('BoardPanel: arrastre sin recalcular layout por frame', () => {
  it('lee los rects una sola vez y solo crea tweens al cambiar el destino', async () => {
    const { cards, reads } = await montar()
    cards[0]!.dispatchEvent(ptr('pointerdown', 10))
    const lecturasAlArmar = reads.mock.calls.length
    gsapMock.to.mockClear()
    for (let y = 12; y <= 40; y += 2) window.dispatchEvent(ptr('pointermove', y))
    expect(reads.mock.calls.length).toBe(lecturasAlArmar)
    expect(gsapMock.to).not.toHaveBeenCalled()
    window.dispatchEvent(ptr('pointermove', 180))
    expect(gsapMock.to).toHaveBeenCalled()
    gsapMock.to.mockClear()
    for (let y = 181; y <= 190; y++) window.dispatchEvent(ptr('pointermove', y))
    expect(reads.mock.calls.length).toBe(lecturasAlArmar)
    expect(gsapMock.to).not.toHaveBeenCalled()
    window.dispatchEvent(ptr('pointercancel', 190))
  })
})

describe('BoardPanel: autoscroll lento', () => {
  it('a velocidad menor a 1px por frame igual avanza (acumula fracciones)', async () => {
    const frames: FrameRequestCallback[] = []
    const raf = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => frames.push(cb))
    const caf = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    const { cards, root } = await montar()
    const sc = root.querySelector('.scroll') as HTMLElement
    sc.getBoundingClientRect = () => ({ top: 0, bottom: 600, height: 600, left: 0, right: 0, width: 0, x: 0, y: 0, toJSON: () => ({}) })
    let top = 0
    Object.defineProperty(sc, 'scrollTop', { configurable: true, get: () => top, set: (v: number) => { top = Math.trunc(v) } })
    cards[0]!.dispatchEvent(ptr('pointerdown', 10))
    window.dispatchEvent(ptr('pointermove', 546))
    for (let i = 0; i < 12; i++) frames.shift()?.(0)
    expect(top).toBeGreaterThanOrEqual(2)
    window.dispatchEvent(ptr('pointercancel', 546))
    raf.mockRestore()
    caf.mockRestore()
  })
})
