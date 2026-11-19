import { describe, expect, it } from 'vitest'
import { DEFAULT_LOGO, LOGO_VARIANTS, abejaGeo, hexPoints, iconSvg, isLogoVariant, monoGeo, panalGeo } from './colmena'
import { litCount, markMode } from '../components/logo/marca'

describe('geometría de Colmena', () => {
  it('el panal tiene centro y seis celdas que no se pisan y entran en el cuadro', () => {
    const g = panalGeo()
    expect(g.ring).toHaveLength(6)
    const all = [g.center, ...g.ring]
    for (const a of all)
      for (const b of all) if (a !== b) expect(Math.hypot(a.x - b.x, a.y - b.y)).toBeGreaterThan(Math.sqrt(3) * g.r)
    for (const c of all) for (const p of hexPoints(c.x, c.y, g.r)) expect(p.x > 0 && p.x < 64 && p.y > 0 && p.y < 64).toBe(true)
  })

  it('el monograma arma una C de nueve celdas con la abeja en la abertura', () => {
    const g = monoGeo()
    expect(g.arc).toHaveLength(9)
    expect(Math.max(...g.arc.map((c) => c.x))).toBeLessThan(g.bee.x)
  })

  it('la abeja arranca en un vértice del hexágono grande', () => {
    const g = abejaGeo()
    expect(g.track.startsWith(`M${+g.bee.x.toFixed(2)} ${+g.bee.y.toFixed(2)}`)).toBe(true)
  })

  it('cada variante genera un SVG de ícono', () => {
    for (const v of LOGO_VARIANTS) expect(iconSvg(v)).toMatch(/^<svg[^>]+viewBox="0 0 512 512".*<\/svg>$/)
  })

  it('valida variantes', () => {
    expect(isLogoVariant('abeja')).toBe(true)
    expect(isLogoVariant('orbita')).toBe(false)
    expect(isLogoVariant(3)).toBe(false)
    expect(LOGO_VARIANTS).toContain(DEFAULT_LOGO)
  })
})

describe('estado de la marca', () => {
  it('enciende una celda por sesión trabajando, con tope', () => {
    expect(litCount({ active: 3 }, 6)).toBe(3)
    expect(litCount({ active: 11 }, 6)).toBe(6)
    expect(litCount({ working: true }, 6)).toBe(1)
    expect(litCount({}, 6)).toBe(0)
  })

  it('sin conexión o como cargador no enciende celdas', () => {
    expect(litCount({ active: 4, live: false }, 6)).toBe(0)
    expect(litCount({ active: 4, loader: true }, 6)).toBe(0)
  })

  it('el modo prioriza cargador, después alerta', () => {
    expect(markMode({ loader: true, attention: true })).toBe('loader')
    expect(markMode({ attention: true, active: 2 })).toBe('attention')
    expect(markMode({ active: 2 })).toBe('working')
    expect(markMode({})).toBe('idle')
  })
})
