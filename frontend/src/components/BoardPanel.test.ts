import { readFileSync } from 'node:fs'
import { createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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
  ordenGuardado: ref(['w2', 'w1']),
  ordenError: ref(''),
  plegadasError: ref(''),
  plegadasGuardado: ref([]),
  hayOrdenManual: ref(true),
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
    render(this: { ws: Workspace }) {
      return h('div', { class: 'ws', 'data-ws-id': this.ws.id })
    },
  },
}))
vi.mock('./LimpiezaChip.vue', () => ({ default: { render: () => null } }))
vi.mock('./MudanzaChip.vue', () => ({ default: { render: () => null } }))
vi.mock('./MudanzaSheet.vue', () => ({ default: { render: () => null } }))
vi.mock('./NuevaTerminalSheet.vue', () => ({ default: { render: () => null } }))
vi.mock('./RetomarSesionSheet.vue', () => ({ default: { render: () => null } }))
vi.mock('./Icon.vue', () => ({ default: { render: () => null } }))
vi.mock('./ViewFrame.vue', () => ({
  default: { props: ['title'], render(this: { $slots: { default?: () => unknown } }) { return this.$slots.default?.() } },
}))
vi.mock('./EmptyState.vue', () => ({ default: { render: () => null } }))

const { default: BoardPanel } = await import('./BoardPanel.vue')
const { destinoReordenQuieto, idDeWorkspace, moverEnOrden, ordenTrasArrastreQuietos, wsEsActivoParaOrden } = await import('../lib/order')

const mk = (id: string, number: number): Workspace => ({
  id,
  number,
  label: id,
  pinned: false,
  status: 'idle',
  tabs: [{ id: `${id}:t1`, label: '1', agents: [] }],
})

beforeEach(() => {
  boardRef.value = {
    updated_at: new Date().toISOString(),
    focused_tab_id: null,
    self_pane_id: null,
    workspaces: [mk('w1', 1), mk('w2', 2)],
    terminales: 'ok',
    conflictos: [],
    caidos: [],
  }
})

const mkWorking = (id: string, number: number): Workspace => ({
  ...mk(id, number),
  tabs: [
    {
      id: `${id}:t1`,
      label: '1',
      agents: [
        {
          pane_id: `${id}:p1`,
          kind: 'claude',
          status: 'working',
          session_id: 's',
          title: 't',
          doing: '',
          pending: '',
          asks_user: false,
          last_activity: null,
        },
      ],
    },
  ],
})

describe('destinoReordenQuieto', () => {
  it('salta activas al subir o bajar', () => {
    const list = [mkWorking('a', 1), mk('q1', 2), mk('q2', 3), mk('q3', 4)]
    expect(destinoReordenQuieto(2, -1, list)).toBe(1)
    expect(destinoReordenQuieto(1, -1, list)).toBe(null)
    expect(destinoReordenQuieto(1, 1, list)).toBe(2)
    expect(destinoReordenQuieto(3, 1, list)).toBe(null)
    expect(wsEsActivoParaOrden(list[0]!)).toBe(true)
  })
})

describe('BoardPanel reorder-move', () => {
  it('mueve entre quietas y arma el orden guardado (activa fija)', () => {
    const list = [mkWorking('a', 1), mk('q1', 2), mk('q2', 3), mk('q3', 4)]
    const visual = list.map(idDeWorkspace)
    const esActivo = (id: string) => wsEsActivoParaOrden(list.find((w) => w.id === id)!)
    const from = 2
    const to = destinoReordenQuieto(from, -1, list)!
    const guardado = ordenTrasArrastreQuietos(moverEnOrden(visual, from, to), esActivo, ['a', 'q1', 'q2', 'q3'])
    expect(guardado.filter((id) => id !== 'a')).toEqual(['q2', 'q1', 'q3'])
  })
})

describe('BoardPanel orden manual', () => {
  it('renderiza las tarjetas según el orden guardado', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(BoardPanel) }))
  const ids = [...html.matchAll(/data-ws-id="([^"]+)"/g)].map((m) => m[1])
    expect(ids).toEqual(['w2', 'w1'])
  })

  it('conecta reorder-move en WorkspaceCard', () => {
    const src = readFileSync('src/components/BoardPanel.vue', 'utf8')
    expect(src).toMatch(/@reorder-move="onReorderMove\(i, \$event\)"/)
  })

  it('tiene el botón de retomar con aria-label', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(BoardPanel) }))
    expect(html).toContain('aria-label="Retomar una sesión vieja"')
  })
})

describe('BoardPanel carteles', () => {
  it('todos los carteles de estado anuncian role="status"', () => {
    const src = readFileSync('src/components/BoardPanel.vue', 'utf8')
    const carteles = [...src.matchAll(/<div [^>]*class="banner"[^>]*>/g)].map((m) => m[0])
    expect(carteles.length).toBeGreaterThanOrEqual(4)
    for (const c of carteles) expect(c).toContain('role="status"')
  })
})
