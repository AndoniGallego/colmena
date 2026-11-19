import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../motion', async () => {
  const { ref } = await import('vue')
  return {
    gsap: {
      set() {},
      to() {},
      fromTo() {},
      from() {},
      timeline: () => ({ to() { return this }, fromTo() { return this }, kill() {} }),
      delayedCall() {},
      utils: { random: () => 1 },
    },
    isSoft: () => true,
    soft: ref(true),
    brandHop: ref(0),
    useGsap: () => ({ run: (fn: () => void) => fn() }),
  }
})

describe('LogoPanal', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  const render = async (props: Record<string, unknown>) => {
    const { default: LogoPanal } = await import('./LogoPanal.vue')
    return renderToString(createSSRApp({ render: () => h(LogoPanal, props) }))
  }

  it('sin cells se ve como siempre', async () => {
    const html = await render({ active: 2 })
    expect(html).not.toContain('data-cell')
    expect(html).toContain('data-mode="working"')
  })

  it('con cells marca cada celda en orden', async () => {
    const html = await render({ cells: ['te-toca', 'trabajando', 'termino', 'tranquila', 'vacia', 'trabajando'] })
    expect(html).toContain('data-cells')
    expect([...html.matchAll(/data-cell="([a-z-]+)"/g)].map((m) => m[1])).toEqual([
      'te-toca',
      'trabajando',
      'termino',
      'tranquila',
      'vacia',
      'trabajando',
    ])
  })

  it('si faltan celdas las completa vacías', async () => {
    const html = await render({ cells: ['te-toca'] })
    expect([...html.matchAll(/data-cell="([a-z-]+)"/g)].map((m) => m[1])).toEqual([
      'te-toca',
      'vacia',
      'vacia',
      'vacia',
      'vacia',
      'vacia',
    ])
  })
})
