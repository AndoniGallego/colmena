// @vitest-environment jsdom
import { createApp, h, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { Board, Workspace } from '../api/types'

vi.mock('../motion', () => ({
  gsap: { from: () => {}, fromTo: () => {}, to: () => {}, set: () => {}, timeline: () => ({ fromTo: () => ({}), to: () => ({}) }) },
  Flip: { getState: () => null, from: () => ({ progress: () => ({ kill: () => {} }) }) },
  isSoft: () => true,
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
const seen: Record<string, unknown[]> = {}
vi.mock('./WorkspaceCard.vue', () => ({
  default: {
    props: ['ws', 'now', 'reorder'],
    emits: ['reorder-move', 'reorder-key', 'grip-down', 'grip-cancel-hold', 'toggle-plegada'],
    render(this: { ws: Workspace; reorder: unknown }) {
      ;(seen[this.ws.id] ??= []).push(this.reorder)
      return h('div', { class: 'ws' })
    },
  },
}))
for (const n of ['LimpiezaChip', 'MudanzaChip', 'MudanzaSheet', 'NuevaTerminalSheet', 'RetomarSesionSheet', 'Icon', 'EmptyState'])
  vi.doMock(`./${n}.vue`, () => ({ default: { render: () => null } }))
vi.mock('./ViewFrame.vue', () => ({
  default: { props: ['title'], render(this: { $slots: { default?: () => unknown } }) { return this.$slots.default?.() } },
}))

const { default: BoardPanel } = await import('./BoardPanel.vue')

const mk = (id: string, number: number, label = id): Workspace => ({
  id, number, label, pinned: false, status: 'idle', tabs: [{ id: `${id}:t1`, label: '1', agents: [] }],
})
const mkBoard = (label: string): Board => ({
  updated_at: new Date().toISOString(), focused_tab_id: null, self_pane_id: null,
  workspaces: [mk('w1', 1, label), mk('w2', 2)], terminales: 'ok', conflictos: [], caidos: [],
})

describe('BoardPanel: reorder estable', () => {
  it('dos renders sin cambio de orden pasan el mismo objeto reorder a cada tarjeta', async () => {
    boardRef.value = mkBoard('a')
    const el = document.createElement('div')
    createApp({ render: () => h(BoardPanel) }).mount(el)
    await nextTick()
    boardRef.value = mkBoard('b')
    await nextTick()
    const r = seen['w2']
    expect(r.length).toBeGreaterThanOrEqual(2)
    expect(r[0]).toBeTruthy()
    expect(r[r.length - 1]).toBe(r[0])
  })
})
