import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import ListoOverlay from './ListoOverlay.vue'

vi.mock('../motion', () => ({
  gsap: { fromTo: vi.fn() },
  haptic: vi.fn(),
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))

describe('ListoOverlay', () => {
  it('renderiza el texto y role="status"', async () => {
    const html = await renderToString(createSSRApp({ render: () => h(ListoOverlay, { texto: 'Nota guardada', visible: true }) }))
    expect(html).toContain('role="status"')
    expect(html).toContain('Nota guardada')
  })
})
