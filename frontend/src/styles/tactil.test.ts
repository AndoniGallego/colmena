import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const readStyle = (name: string) =>
  readFileSync(new URL(`./${name}`, import.meta.url).pathname, 'utf8')

const readVue = (rel: string) =>
  readFileSync(new URL(`../components/${rel}`, import.meta.url).pathname, 'utf8')

function templateOf(vue: string) {
  const start = vue.indexOf('<template>')
  const styleStart = vue.indexOf('<style', start)
  if (start < 0 || styleStart < 0) return ''
  const inner = vue.slice(start + '<template>'.length, styleStart)
  const end = inner.lastIndexOf('</template>')
  return end < 0 ? inner : inner.slice(0, end)
}

function hasClassHit(tpl: string, token: string) {
  const re = new RegExp(`<button[^>]*class="[^"]*\\b${token}\\b[^"]*\\bhit\\b[^"]*"`, 's')
  return re.test(tpl)
}

describe('zonas táctiles .hit', () => {
  it('ui.css define .hit::after en @media (pointer: coarse)', () => {
    const css = readStyle('ui.css')
    expect(css).toMatch(/@media\s*\(\s*pointer:\s*coarse\s*\)[\s\S]*\.hit::after/)
  })

  it('AgentRow: respond, pide y mr-chip llevan hit', () => {
    const tpl = templateOf(readVue('AgentRow.vue'))
    expect(hasClassHit(tpl, 'respond')).toBe(true)
    expect(hasClassHit(tpl, 'pide')).toBe(true)
    expect(hasClassHit(tpl, 'mr-chip')).toBe(true)
  })

  it('SessionChatView: Reintentar (retryLoad) lleva hit', () => {
    const tpl = templateOf(readVue('SessionChatView.vue'))
    const retryBtns = [...tpl.matchAll(/<button\b[^>]*retryLoad[^>]*>/g)].map((m) => m[0])
    expect(retryBtns.length).toBeGreaterThan(0)
    expect(retryBtns.every((b) => /\bhit\b/.test(b))).toBe(true)
  })

  it('SessionChatView: Reintentar y Descartar de un mensaje fallido llevan hit', () => {
    const tpl = templateOf(readVue('SessionChatView.vue'))
    const btns = [...tpl.matchAll(/<button\b[^>]*(?:retryPending|discardPending)[^>]*>/g)].map((m) => m[0])
    expect(btns.length).toBe(2)
    expect(btns.every((b) => /\bhit\b/.test(b))).toBe(true)
  })

  it('QuestionStepper: botones de opción llevan hit', () => {
    const tpl = templateOf(readVue('QuestionStepper.vue'))
    expect(tpl).toMatch(/<button[^>]*class="[^"]*\bopt\b[^"]*\bhit\b[^"]*"/)
  })
})

describe('KitView: filas y botones táctiles', () => {
  const tpl = () => templateOf(readVue('KitView.vue'))
  it('regla, arreglar, reintentar y volver llevan hit', () => {
    const btns = [...tpl().matchAll(/<button\b[^>]*data-test="(?:regla|arreglar|reintentar|volver-regla)"[^>]*>/g)].map((m) => m[0])
    expect(btns.length).toBe(4)
    expect(btns.every((b) => /\bhit\b/.test(b))).toBe(true)
  })
})

describe('touch-action global', () => {
  it('base.css aplica touch-action: manipulation a los controles', () => {
    const css = readStyle('base.css')
    expect(css).toMatch(
      /button,\s*a,\s*\[role='button'\],\s*input,\s*select,\s*textarea,\s*label\s*\{[^}]*touch-action:\s*manipulation/,
    )
  })
})

function styleOf(vue: string) {
  const m = vue.match(/<style[^>]*>([\s\S]*?)<\/style>/)
  return m ? m[1] : ''
}

function coarseBlocks(css: string) {
  const out: string[] = []
  const re = /@media\s*\(\s*pointer:\s*coarse\s*\)\s*\{/g
  let m: RegExpExecArray | null
  while ((m = re.exec(css))) {
    let depth = 1
    let i = m.index + m[0].length
    const start = i
    while (i < css.length && depth > 0) {
      if (css[i] === '{') depth++
      else if (css[i] === '}') depth--
      i++
    }
    out.push(css.slice(start, i - 1))
  }
  return out.join('\n')
}

function classHasHit(tpl: string, token: string) {
  const re = new RegExp(`<(?:button|a|span)\\b[^>]*class="[^"]*\\b${token}\\b[^"]*\\bhit\\b[^"]*"`, 's')
  return re.test(tpl)
}

function coarseRule(vue: string, selector: string, prop: RegExp) {
  const block = coarseBlocks(styleOf(vue))
  const esc = selector.replace(/[.[\]()]/g, '\\$&')
  const re = new RegExp(`${esc}\\s*\\{[^}]*${prop.source}`)
  return re.test(block)
}

describe('S4: controles >= 44px en pointer: coarse', () => {
  it('TerminalComposer: close con hit; chip, h, clear con alto real', () => {
    const vue = readVue('TerminalComposer.vue')
    expect(classHasHit(templateOf(vue), 'close')).toBe(true)
    for (const s of ['.chip', '.h', '.clear']) {
      expect(coarseRule(vue, s, /min-height:\s*44px/)).toBe(true)
    }
  })

  it('TopBar: .stat lleva hit', () => {
    expect(classHasHit(templateOf(readVue('TopBar.vue')), 'stat')).toBe(true)
  })

  it('TopBar: .stat mide 44px reales en coarse (el readout compacto recorta el ::after)', () => {
    expect(coarseRule(readVue('TopBar.vue'), '.stat', /min-height:\s*44px/)).toBe(true)
  })

  it('SegControl: .seg-btn usa max(36px, var(--h-md))', () => {
    expect(readVue('SegControl.vue')).toMatch(/min-height:\s*max\(36px,\s*var\(--h-md\)\)/)
  })

  it('VozButton: .mic lleva hit', () => {
    expect(classHasHit(templateOf(readVue('VozButton.vue')), 'mic')).toBe(true)
  })

  it('TerminalVivo: x y fit con hit; tkey con alto real', () => {
    const vue = readVue('TerminalVivo.vue')
    const tpl = templateOf(vue)
    expect(classHasHit(tpl, 'x')).toBe(true)
    expect(classHasHit(tpl, 'fit')).toBe(true)
    expect(coarseRule(vue, '.tkey', /min-height:\s*44px/)).toBe(true)
  })

  it('BibViewer: .ic con tamaño real de 44px (la botonera está pegada)', () => {
    const vue = readVue('BibViewer.vue')
    expect(coarseRule(vue, '.ic', /min-height:\s*44px/)).toBe(true)
    expect(coarseRule(vue, '.ic', /min-width:\s*44px/)).toBe(true)
  })

  it('SessionChatView: .crumb-back lleva hit', () => {
    expect(classHasHit(templateOf(readVue('SessionChatView.vue')), 'crumb-back')).toBe(true)
  })

  it('PreguntasDock: el chip que contiene .pgo mide 44px', () => {
    expect(coarseRule(readVue('PreguntasDock.vue'), '.pchip', /min-height:\s*44px/)).toBe(true)
  })

  it('MrCard: .sacar lleva hit', () => {
    expect(classHasHit(templateOf(readVue('MrCard.vue')), 'sacar')).toBe(true)
  })

  it('App: .fallback-btn con min-height 44px en coarse', () => {
    expect(coarseRule(readVue('../App.vue'), '.fallback-btn', /min-height:\s*44px/)).toBe(true)
  })
})

describe('cerrar una terminal', () => {
  it('TerminalRow: el × es hermano de la fila (no anidado), lleva hit y no aparece si está protegida', () => {
    const tpl = templateOf(readVue('TerminalRow.vue'))
    expect(hasClassHit(tpl, 'cerrar')).toBe(true)
    const fila = tpl.indexOf('class="trow"')
    const finFila = tpl.indexOf('</button>', fila)
    const x = tpl.search(/<button[^>]*aria-label="Cerrar terminal"/)
    expect(fila).toBeGreaterThan(-1)
    expect(x).toBeGreaterThan(finFila)
    const btnX = tpl.match(/<button[^>]*aria-label="Cerrar terminal"[^>]*>/s)?.[0] ?? ''
    expect(btnX).toContain('v-if="!terminal.protegida"')
    expect(tpl).toContain("openAccion('cerrar', terminal.pane_id)")
  })

  it('TerminalViewer: botón Cerrar terminal aunque la escritura esté apagada', () => {
    const tpl = templateOf(readVue('TerminalViewer.vue'))
    expect(tpl).toContain("openAccion('cerrar', openTerminalId!)")
    expect(tpl).toMatch(/Cerrar terminal/)
    expect(tpl).not.toContain('<TerminalConfirmSheet')
  })

  it('la hoja de confirmar vive en App para que funcione desde el tablero', () => {
    const app = readFileSync(new URL('../App.vue', import.meta.url).pathname, 'utf8')
    expect(app).toContain('<TerminalConfirmSheet')
  })
})
