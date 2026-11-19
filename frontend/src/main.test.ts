import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

describe('main entry', () => {
  it('no importa App.vue de forma estática (el notch no debe arrastrar el bundle entero)', () => {
    const src = readFileSync(new URL('./main.ts', import.meta.url).pathname, 'utf8')
    expect(src).not.toMatch(/^\s*import\s+App\s+from\s+['"]\.\/App\.vue['"]/m)
    expect(src).toMatch(/import\s*\(\s*['"]\.\/App\.vue['"]\s*\)/)
  })
})
