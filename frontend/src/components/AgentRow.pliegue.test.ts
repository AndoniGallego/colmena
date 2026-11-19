import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const src = readFileSync('src/components/AgentRow.vue', 'utf8')
const bloque = (sel: string) => new RegExp(`${sel.replace('.', '\\.')}\\s*\\{[^}]*\\}`, 'g')

describe('AgentRow: despliegue con una sola animación de altura', () => {
  it('no transiciona padding ni height, solo grid-template-rows', () => {
    const css = src.slice(src.indexOf('<style'))
    expect(css).not.toMatch(/transition:[^;]*\bpadding\b/)
    expect(css).not.toMatch(/transition:[^;]*\bheight\b/)
    const drawer = css.match(bloque('.drawer'))![0]
    expect(drawer).toMatch(/transition:\s*grid-template-rows\s+0\.2[0-8]?s\s+var\(--ease-out\)/)
  })

  it('el padding del cajón es fijo y vive en el hijo interno', () => {
    const css = src.slice(src.indexOf('<style'))
    expect(css).not.toMatch(/\.open \.drawer-inner\s*\{[^}]*padding/)
    expect(css).toMatch(/\.panel\s*\{[^}]*padding-bottom:\s*12px/)
  })

  it('al abrir no hay tween de altura ni stagger de botones', () => {
    const js = src.slice(0, src.indexOf('<template'))
    expect(js).not.toMatch(/height:\s*to/)
    expect(js).not.toMatch(/stagger/)
  })
})
