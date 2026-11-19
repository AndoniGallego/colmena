import { describe, expect, it } from 'vitest'

const files = import.meta.glob('../components/Terminal*.vue', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('componentes de terminal', () => {
  it('existen y ninguno usa v-html ni innerHTML', () => {
    const names = Object.keys(files)
    expect(names.length).toBeGreaterThanOrEqual(4)
    for (const [name, src] of Object.entries(files)) {
      expect(src, name).not.toMatch(/v-html|innerHTML|insertAdjacentHTML|outerHTML/)
    }
  })
})
