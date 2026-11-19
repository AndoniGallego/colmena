import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const vue = (n: string) => readFileSync(new URL(`./${n}`, import.meta.url).pathname, 'utf8')

function reglaRaiz(src: string, clase: string) {
  const m = src.match(new RegExp(`\\n\\.${clase} \\{([^}]*)\\}`))
  return m ? m[1] : ''
}

describe('KitView se abre como capa encima del tablero', () => {
  it('la raíz es fija a pantalla completa como Ajustes y Entornos', () => {
    const kit = reglaRaiz(vue('KitView.vue'), 'kv')
    expect(kit).toMatch(/position:\s*fixed/)
    expect(kit).toMatch(/inset:\s*0/)
    expect(kit).toMatch(/z-index:\s*80/)
    expect(reglaRaiz(vue('EntornosView.vue'), 'en')).toMatch(/position:\s*fixed/)
  })
})
