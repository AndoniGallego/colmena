import { createSSRApp, defineComponent, h, provide, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { Mr } from '../api/mrsApi'

vi.mock('../motion', () => ({ gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
vi.mock('../state/mrs', () => ({ mrs: { sel: null, busy: null }, pausar: vi.fn() }))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./MrPipe.vue', () => ({ default: { name: 'MrPipe', render: () => null } }))

const { default: MrCard } = await import('./MrCard.vue')

const m: Mr = {
  ref: '7:1',
  project_id: 7,
  iid: 1,
  repo: 'grupo/repo7',
  repo_corto: 'repo7',
  titulo: 'feat: cosa',
  rama: 'feature/x',
  target: 'main',
  rol: 'autor',
  autor: { username: 'yo', nombre: 'Yo' },
  draft: false,
  conflictos: false,
  estado_merge: 'mergeable',
  puede_mergear: true,
  sha: 'a'.repeat(40),
  pipeline: { estado: 'ok', id: 1, url: '' },
  aprobaciones: { dadas: 0, requeridas: 1, faltan: 1, por: [], yo: false, puedo: false },
  reviewers: [],
  hilos_sin_resolver: 0,
  comentarios_nuevos: 0,
  url: '',
  actualizado: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
  creado: '2026-10-31T14:05:00Z',
  pausado: false,
}

const Card = MrCard as typeof MrCard & {
  setup: NonNullable<(typeof MrCard)['setup']>
  ssrRender: (...args: unknown[]) => void
  __scopeId?: string
  props: Record<string, unknown>
}

async function renderCard(props: { m: Mr; now: number; pausado?: boolean }) {
  const Host = defineComponent({
    props: Card.props,
    __scopeId: Card.__scopeId,
    setup(p: typeof props) {
      provide(ssrContextKey, { modules: new Set<string>() })
      return Card.setup(p as Parameters<typeof Card.setup>[0], { emit: () => {}, attrs: {}, slots: {}, expose: () => {} }) as Record<string, unknown>
    },
    ssrRender: Card.ssrRender,
  } as Parameters<typeof defineComponent>[0])
  return renderToString(createSSRApp({ render: () => h(Host, props) }))
}

describe('MrCard', () => {
  it('muestra antigüedad y title de creación', async () => {
    const now = Date.parse('2026-11-03T12:00:00Z')
    const card = { ...m, actualizado: new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString() }
    const html = await renderCard({ m: card, now })
    expect(html).toContain('hace 3 días')
    expect(html).toContain('Creado el')
  })
})
