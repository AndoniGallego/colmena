import { readFileSync, readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const root = new URL('../', import.meta.url).pathname
const read = (rel: string) => readFileSync(root + rel, 'utf8')
const comp = (n: string) => read(`components/${n}`)

function walk(dir: string): string[] {
  return readdirSync(root + dir, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory() ? walk(`${dir}/${d.name}`) : /\.(vue|css)$/.test(d.name) ? [`${dir}/${d.name}`] : [],
  )
}

describe('sin rebote en movimiento frecuente', () => {
  it.each(['MobileTabs.vue', 'MrsView.vue', 'SessionChatView.vue', 'QuestionStepper.vue'])(
    '%s no usa elastic',
    (f) => expect(comp(f)).not.toMatch(/elastic/),
  )
  it('el helper magnético vuelve con power3.out', () => {
    expect(read('motion/index.ts')).not.toMatch(/elastic/)
  })
  it('MobileTabs rota como mucho 8deg', () => {
    const rots = [...comp('MobileTabs.vue').matchAll(/rotation:\s*([^,}]+)/g)].flatMap((m) => [...m[1].matchAll(/\d+/g)].map((n) => Number(n[0])))
    expect(rots.every((n) => n <= 8)).toBe(true)
  })
})

describe('entradas de preguntas cortas y sin rebote', () => {
  const entradas = (f: string) =>
    comp(f).split('\n').filter((l) => /\.from\(q\('\.pane \.opt|\.from\(sel\('\.opt|gsap\.from\(el\.parentElement/.test(l))
  it.each(['PreguntasDock.vue', 'QuestionStepper.vue'])('%s entra con power3.out <= 0.3s', (f) => {
    const ls = entradas(f)
    expect(ls.length).toBeGreaterThan(0)
    for (const l of ls) {
      expect(l).toMatch(/ease:\s*'power3\.out'/)
      expect(Number(/duration:\s*([\d.]+)/.exec(l)![1])).toBeLessThanOrEqual(0.3)
    }
    expect(comp(f)).not.toMatch(/back\.out/)
  })
})

describe('sin blur animado', () => {
  it.each(['QuestionStepper.vue', 'PreguntasDock.vue'])('%s no anima filter', (f) => {
    expect(comp(f)).not.toMatch(/filter:\s*'blur/)
  })
  it.each(['AvisosBell.vue', 'ListoOverlay.vue'])('%s oscurece sin blur', (f) => {
    expect(comp(f)).not.toMatch(/backdrop-filter:\s*blur/)
  })
  it('AvisosBell mantiene el oscurecido del fondo', () => {
    expect(comp('AvisosBell.vue')).toMatch(/\.back\s*\{[^}]*background:\s*rgb\(/)
  })
  it('el scrim no usa backdrop-filter', () => {
    const css = read('styles/ui.css')
    const scrim = css.match(/\.sheet-scrim\s*\{[^}]*\}/)![0]
    expect(scrim).not.toMatch(/backdrop-filter/)
  })
})

describe('tokens de movimiento', () => {
  const base = read('styles/base.css')
  it('define --press-scale y --ease-sheet', () => {
    expect(base).toMatch(/--press-scale:\s*0\.96/)
    expect(base).toMatch(/--ease-sheet:\s*cubic-bezier\(0\.32,\s*0\.72,\s*0,\s*1\)/)
  })
  it.each(['ConfirmSheet.vue', 'BibQuitarSheet.vue'])('%s entra con --ease-sheet', (f) => {
    expect(comp(f)).toMatch(/\.qs-enter-active \.qs\s*\{\s*transition:\s*transform 0\.[45]\d?s var\(--ease-sheet\)/)
  })
  it('ningún :active escala por debajo de 0.96', () => {
    for (const f of walk('.')) {
      if (f.endsWith('.test.ts')) continue
      const src = read(f)
      for (const m of src.matchAll(/[^{}]*:active[^{}]*\{([^{}]*)\}/g)) {
        expect(m[1], f).not.toMatch(/scale:\s*0\.(8\d?|9[0-5]?)\b/)
        expect(m[1], f).not.toMatch(/scale\(0\.(8\d?|9[0-5]?)\)/)
      }
    }
  })
  it('.btn-back y AttachChip usan --press-scale', () => {
    expect(read('styles/ui.css')).toMatch(/\.btn-back:active[^{]*\{\s*scale:\s*var\(--press-scale\)/)
    expect(comp('AttachChip.vue')).toMatch(/:active\s*\{\s*scale:\s*var\(--press-scale\)/)
  })
})

describe('respeta reduced-motion vía isSoft', () => {
  it('SessionChatView no lee matchMedia directo', () => {
    expect(comp('SessionChatView.vue')).not.toMatch(/matchMedia\('\(prefers-reduced-motion/)
  })
  it('SessionChatView y BoardPanel importan isSoft', () => {
    expect(comp('SessionChatView.vue')).toMatch(/import \{[^}]*isSoft[^}]*\} from '\.\.\/motion'/)
    expect(comp('BoardPanel.vue')).toMatch(/import \{[^}]*isSoft[^}]*\} from '\.\.\/motion'/)
  })
})
