import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// Las animaciones infinitas corren mientras la pantalla está prendida: si animan algo que no compone la GPU
// (sombras, posición de fondo, tamaños, filtros) obligan a repintar en cada cuadro y gastan batería en el celu.
const rawVue = import.meta.glob('../**/*.vue', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const rawCss: Record<string, string> = Object.fromEntries(
  ['base.css', 'ui.css'].map((f) => [`./${f}`, readFileSync(new URL(`./${f}`, import.meta.url).pathname, 'utf8')]),
)

const REPINTA = /(?:^|[;{\s])(box-shadow|background-position(?:-[xy])?|background|width|height|top|left|right|bottom|filter|margin|padding)\s*:/

function keyframes(text: string): Map<string, string> {
  const out = new Map<string, string>()
  const re = /@keyframes\s+([\w-]+)\s*\{/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text))) {
    let depth = 1
    let i = re.lastIndex
    while (i < text.length && depth > 0) {
      if (text[i] === '{') depth++
      else if (text[i] === '}') depth--
      i++
    }
    out.set(m[1], text.slice(re.lastIndex, i - 1))
  }
  return out
}

function nombresInfinitos(text: string): string[] {
  const out: string[] = []
  for (const m of text.matchAll(/animation\s*:([^;}]*)/g)) {
    for (const parte of m[1].split(',')) {
      if (!/\binfinite\b/.test(parte)) continue
      out.push(...(parte.match(/[a-zA-Z_][\w-]*/g) ?? []))
    }
  }
  return out
}

describe('animaciones infinitas', () => {
  it('solo animan transform u opacity (no repintan en cada cuadro)', () => {
    const globales = new Map<string, string>()
    for (const css of Object.values(rawCss)) for (const [k, v] of keyframes(css)) globales.set(k, v)
    const malas: string[] = []
    const archivos = { ...rawCss, ...rawVue }
    for (const [ruta, texto] of Object.entries(archivos)) {
      if (ruta.includes('.test.')) continue
      const locales = keyframes(texto)
      for (const nombre of new Set(nombresInfinitos(texto))) {
        const cuerpo = locales.get(nombre) ?? globales.get(nombre)
        if (cuerpo === undefined) continue
        const prop = cuerpo.match(REPINTA)
        if (prop) malas.push(`${ruta.replace(/^\.\.\//, 'src/').replace(/^\.\//, 'src/styles/')}: @keyframes ${nombre} anima ${prop[1]}`)
      }
    }
    expect(malas).toEqual([])
  })
})

describe('consumo en el celu', () => {
  const vue = (nombre: string) => rawVue[`../components/${nombre}`]

  it('las barras fijas no difuminan lo de atrás en pantallas táctiles', () => {
    for (const nombre of ['TopBar.vue', 'MobileTabs.vue', 'ViewFrame.vue', 'ViewHeader.vue']) {
      expect(vue(nombre), nombre).toMatch(/@media\s*\(pointer:\s*coarse\)\s*\{[^@]*backdrop-filter:\s*none/)
    }
  })

  // content-visibility recortaría el menú y el grip, que salen del borde de la tarjeta: se pausa por atributo.
  it('las tarjetas del tablero fuera de la vista no se animan', () => {
    expect(vue('WorkspaceCard.vue')).toMatch(/observarFueraDeVista\(/)
    expect(rawCss['./base.css']).toMatch(/\[data-fuera\]\s+\*::after[^{]*\{[^}]*animation-play-state:\s*paused/)
  })
})
