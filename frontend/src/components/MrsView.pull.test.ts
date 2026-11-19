import { describe, expect, it } from 'vitest'
import src from './MrsView.vue?raw'

describe('MrsView pull-to-refresh', () => {
  it('no guarda el tirón en un ref reactivo ni anima la altura', () => {
    expect(src).not.toMatch(/const pull = ref\(/)
    expect(src).not.toMatch(/height: `\$\{pull\}px`/)
    expect(src).not.toMatch(/transition: height/)
  })
  it('escribe el indicador directo con transform y mantiene el umbral de 60', () => {
    expect(src).toMatch(/el\.style\.transform = `translate/)
    expect(src).toMatch(/pullDist >= 60/)
  })
  it('la transición va solo al soltar, no durante el arrastre', () => {
    expect(src).toMatch(/soltar && !isSoft\(\) \? 'transform 0\.25s[^']*' : ''/)
    expect(src).not.toMatch(/\.pull-ind\s*\{[^}]*transition/)
  })
})
