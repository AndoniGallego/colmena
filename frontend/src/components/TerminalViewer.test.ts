import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('TerminalViewer', () => {
  it('no incluye botón Enfocar', () => {
    const src = readFileSync(new URL('./TerminalViewer.vue', import.meta.url).pathname, 'utf8')
    expect(src).not.toContain('Enfocar')
    expect(src).not.toContain('focusTab')
  })
})
