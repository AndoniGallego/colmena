import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const css = (f: string) => readFileSync(`src/components/${f}`, 'utf8')
const baseCss = () => readFileSync('src/styles/base.css', 'utf8')

describe('marco común de vistas', () => {
  it('ViewFrame usa el gutter compartido', () => {
    expect(css('ViewFrame.vue')).toMatch(/var\(--gutter\)/)
  })
  it('el chat usa el ancho del panel y la caja de texto queda en 880px', () => {
    expect(baseCss()).toMatch(/--read-max:\s*880px/)
    expect(baseCss()).toMatch(/--chat-max:\s*1240px/)
    for (const f of ['SessionChatView.vue']) {
      expect(css(f)).toMatch(/\.thread[^{]*\{[^}]*max-width:\s*var\(--chat-max\)/)
      expect(css(f)).toMatch(/\.dock\s*\{[^}]*max-width:\s*var\(--read-max\)/)
    }
  })
})

describe('guarda de ancho del tablero', () => {
  it('la lista de workspaces usa una columna que puede encogerse', () => {
    expect(css('BoardPanel.vue')).toMatch(/\.list\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/)
  })
  it('el scroll del tablero no scrollea en horizontal', () => {
    expect(css('BoardPanel.vue')).toMatch(/\.scroll\s*\{[^}]*overflow-x:\s*hidden/)
  })
  it('las tarjetas y filas pueden encogerse', () => {
    expect(css('WorkspaceCard.vue')).toMatch(/\.ws\s*\{[^}]*min-width:\s*0/)
    expect(css('TerminalRow.vue')).toMatch(/\.trow\s*\{[^}]*min-width:\s*0/)
    expect(css('TerminalGroup.vue')).toMatch(/\.tgroup\s*\{[^}]*min-width:\s*0/)
  })
})

import { normalizeTerminalSalida } from '../api/normalize'

describe('motivo de escritura', () => {
  it('conserva solo motivos conocidos', () => {
    expect(normalizeTerminalSalida({ puede_escribir: false, motivo: 'ocupada' })).toMatchObject({ puede_escribir: false, motivo: 'ocupada' })
    expect(normalizeTerminalSalida({ puede_escribir: true, motivo: 'raro' })).toMatchObject({ puede_escribir: true, motivo: null })
    expect(normalizeTerminalSalida({})).toMatchObject({ puede_escribir: false, motivo: null })
  })
})
