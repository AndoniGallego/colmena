import { describe, expect, it } from 'vitest'
import src from './BibliotecaView.vue?raw'

describe('BibliotecaView visor móvil', () => {
  it('el visor deja scroll nativo y limita touch-action none a la zona del swipe de cierre', () => {
    expect(src).toMatch(/\.m-viewer\s*\{[^}]*touch-action:\s*pan-y/)
    expect(src).not.toMatch(/\.m-viewer\s*\{[^}]*touch-action:\s*none/)
    expect(src).toMatch(/\.m-viewer\s+:deep\(\.bar\)[^{]*\{[^}]*touch-action:\s*none/)
  })
  it('al tocar de nuevo se cortan los tweens del regreso', () => {
    expect(src).toMatch(/function sDown[\s\S]*?gsap\.killTweensOf\(sheet\.value\)/)
  })
  it('pointercancel no cuenta como soltar: vuelve a su lugar sin cerrar ni cambiar', () => {
    const body = src.match(/function sUp[\s\S]*?\n\}/)![0]
    expect(body).toMatch(/if \(e\.type === 'pointercancel'\) \{\s*if \(st\.lock\) settle\(\)\s*return\s*\}[\s\S]*closeViewer/)
  })
  it('la hoja de filtros entra con --ease-sheet, sin rebote', () => {
    expect(src).toMatch(/\.sheet-enter-active \.sheet\s*\{\s*transition:\s*transform 0\.[2-5]\d?s var\(--ease-sheet\)/)
    expect(src).not.toMatch(/\.sheet-enter-active \.sheet\s*\{[^}]*--spring/)
  })
})
