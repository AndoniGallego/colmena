import { createSSRApp, h, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

const mrsDestino = reactive({ open: true, cual: { tipo: 'job', id: 1 }, sesiones: [], sugerida: null, busy: false, error: '' })
vi.mock('../state/mrs', () => ({ mrsDestino, cerrarDestino: vi.fn(), elegirDestino: vi.fn() }))
vi.mock('../motion', () => ({ gsap: {}, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
vi.mock('../lib/focusTrap', () => ({ useFocusTrap: () => ({ onKeydown: () => {} }) }))
vi.mock('../lib/useSheetSwipe', () => ({ useSheetSwipe: () => {} }))
vi.mock('./InlineAlert.vue', () => ({ default: { template: '<div />' } }))

const { default: Sheet } = await import('./MrDestinoSheet.vue')
const { default: css } = (await import('./MrDetail.vue?raw')) as { default: string }

describe('MrDestinoSheet', () => {
  it('cada instancia usa un id de título propio', async () => {
    const ctx: { teleports?: Record<string, string> } = {}
    await renderToString(createSSRApp({ render: () => h('div', [h(Sheet), h(Sheet)]) }), ctx)
    const ids = [...(ctx.teleports?.body ?? '').matchAll(/<h2 id="([^"]+)"/g)].map((m) => m[1])
    expect(ids).toHaveLength(2)
    expect(new Set(ids).size).toBe(2)
    expect(ctx.teleports?.body).not.toContain('"md-title"')
  })
})

describe('MrDetail: filas con botones nuevos', () => {
  it('el wrap y el gap son solo de las filas con botones de mandar', () => {
    expect(css).not.toMatch(/\n\.job \{ flex-wrap: wrap; \}/)
    expect(css).toMatch(/\.job\.con-mandar \{[^}]*flex-wrap: wrap[^}]*\}/)
    expect(css).toMatch(/\.job\.con-mandar \{[^}]*gap: 12px[^}]*\}/)
  })
})
