import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const vue = (rel: string) => readFileSync(new URL(`../components/${rel}`, import.meta.url).pathname, 'utf8')

describe('teclado virtual en RetomarSesionSheet', () => {
  it('usa useKeyboard y aplica el layout al sheet-root', () => {
    const src = vue('RetomarSesionSheet.vue')
    expect(src).toMatch(/import \{ useKeyboard \} from '..\/lib\/keyboard'/)
    expect(src).toMatch(/useKeyboard\(\)/)
    expect(src).toMatch(/class="sheet-root rs" :style="layout"/)
  })
})

describe('bordes seguros laterales', () => {
  it.each(['MobileTabs.vue', 'ViewFrame.vue'])('%s contempla safe-area-inset-left y -right', (f) => {
    const src = vue(f)
    expect(src).toContain('safe-area-inset-left')
    expect(src).toContain('safe-area-inset-right')
  })

  it('ViewFrame aplica max(var(--gutter), safe-area) en cabecera y cuerpos', () => {
    const src = vue('ViewFrame.vue')
    expect(src.match(/max\(var\(--gutter\), [a-z]+\(safe-area-inset-left\)\)/g)?.length).toBeGreaterThanOrEqual(3)
  })

  it('MobileTabs ancla el slider con el mismo inset que el padding', () => {
    const src = vue('MobileTabs.vue')
    expect(src).toMatch(/\.tabs\s*\{[^}]*--tabs-pl:\s*max\(12px, [a-z]+\(safe-area-inset-left\)\)/s)
    expect(src).toMatch(/\.tabs\s*\{[^}]*--tabs-pr:\s*max\(12px, [a-z]+\(safe-area-inset-right\)\)/s)
    expect(src).toMatch(/\.slider\s*\{[^}]*left:\s*var\(--tabs-pl\)/s)
    expect(src).toMatch(/width: `calc\(\(100% - var\(--tabs-pl\) - var\(--tabs-pr\) \+ 24px\)/)
  })

  it('ui.css .view-body respeta los bordes laterales', () => {
    const css = readFileSync(new URL('./ui.css', import.meta.url).pathname, 'utf8')
    expect(css).toMatch(/\.view-body\s*\{[^}]*safe-area-inset-left/s)
    expect(css).toMatch(/\.view-body\s*\{[^}]*safe-area-inset-right/s)
  })

  it('LoginScreen suma safe-area-inset-top y -bottom', () => {
    const src = vue('LoginScreen.vue')
    expect(src).toMatch(/\.login\s*\{[^}]*safe-area-inset-top/s)
    expect(src).toMatch(/\.login\s*\{[^}]*safe-area-inset-bottom/s)
  })
})

describe('overscroll en scroll interno', () => {
  it.each([
    'DialogCard.vue', 'PedidoCard.vue', 'PedidoPestanaCard.vue', 'BibViewer.vue',
    'EntornosView.vue', 'notch/NotchPill.vue',
  ])('%s con overflow auto/scroll define overscroll-behavior', (f) => {
    const src = vue(f)
    const n = (src.match(/overflow(-y)?:\s*(auto|scroll)/g) ?? []).length
    expect(n).toBeGreaterThan(0)
    expect((src.match(/overscroll-behavior:\s*contain/g) ?? []).length).toBeGreaterThanOrEqual(n)
  })
})
