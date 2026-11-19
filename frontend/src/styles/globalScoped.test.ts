import { describe, expect, it } from 'vitest'

const rawVue = import.meta.glob('../**/*.vue', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

// Vue descarta lo que sigue a `:global(...)` en un selector ('<global> .x' queda solo como '<global>').
const GLOBAL_CON_COLA = /:global\([^)]*\)[ \t]+[.#\[:\w>+~*]/g

describe('estilos scoped', () => {
  it('no usan :global(...) seguido de otro selector', () => {
    const malos: string[] = []
    for (const [ruta, texto] of Object.entries(rawVue)) {
      for (const b of texto.matchAll(/<style[^>]*\bscoped\b[^>]*>([\s\S]*?)<\/style>/gi)) {
        for (const m of b[1].matchAll(GLOBAL_CON_COLA)) malos.push(`${ruta.replace('../', 'src/')}: ${m[0]}`)
      }
    }
    expect(malos).toEqual([])
  })
})
