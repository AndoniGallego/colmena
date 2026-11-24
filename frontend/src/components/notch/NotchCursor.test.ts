import { describe, expect, it } from 'vitest'

const fuente = (await import('./NotchApp.vue?raw')).default as string
const global = fuente.slice(fuente.indexOf('<style>'), fuente.indexOf('</style>'))

describe('cursor del notch', () => {
  it('todo lo clicable del notch muestra la manito desde una sola regla base', () => {
    const regla = global.match(/:where\(html\.notch\)[^{]*\{[^}]*\}/)?.[0] ?? ''
    for (const sel of ['button', "[role='button']", 'a[href]', 'summary', 'label[for]']) {
      expect(regla).toContain(sel)
    }
    expect(regla).toMatch(/cursor:\s*pointer/)
  })

  it('lo deshabilitado no muestra la manito', () => {
    const regla = global.match(/:where\(html\.notch\)[^{]*\{[^}]*\}/)?.[0] ?? ''
    expect(regla).toMatch(/:not\([^)]*:disabled/)
  })
})
