import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const leer = (f: string) => readFileSync(new URL(f, import.meta.url).pathname, 'utf8')
const mediaCelu = (css: string) => {
  const i = css.indexOf('@media (max-width: 440px)')
  expect(i).toBeGreaterThan(-1)
  return css.slice(i, css.indexOf('\n}\n', i))
}

// La barra a 390px medía 420 con la pastilla del plan (390 sin ella): en celu ahorra lo que la pastilla ocupa.
describe('TopBar con la pastilla del plan a 390px', () => {
  const topbar = mediaCelu(leer('./TopBar.vue'))

  it('en celu saca el punto de conexión y achica botones y huecos', () => {
    expect(topbar).toMatch(/\.compact \.conn \{ display: none; \}/)
    expect(topbar).toMatch(/\.compact \.right \{ gap: 2px; \}/)
    expect(topbar).toMatch(/\.bell\) \{ width: 28px; \}/)
  })

  it('la pastilla compacta mide 26px y puede achicarse (min-width: 0)', () => {
    const pill = mediaCelu(leer('./UsoPlanPill.vue'))
    expect(pill).toMatch(/\.compact \.pill \{ width: 26px; \}/)
    expect(pill).toMatch(/min-width: 0/)
  })
})
