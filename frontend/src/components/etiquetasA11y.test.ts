import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const leer = (ruta: string) => readFileSync(ruta, 'utf8')

describe('etiquetas de accesibilidad', () => {
  it('los campos de respuesta libre del notch tienen aria-label', () => {
    const src = leer('src/components/notch/NotchFila.vue')
    const inputs = [...src.matchAll(/<input\b[^>]*?>/gs)].map((m) => m[0]).filter((i) => i.includes('inputLibre'))
    expect(inputs.length).toBe(2)
    for (const i of inputs) expect(i).toContain('aria-label=')
  })

  it('la carga del notch se anuncia como estado', () => {
    expect(leer('src/components/notch/NotchFila.vue')).toMatch(/<p class="skel" role="status" aria-label="Cargando">/)
  })

  it('el buscador tiene aria-label', () => {
    const src = leer('src/components/CommandPalette.vue')
    const input = src.match(/<input\b[^>]*?class="pal-input"[^>]*?>/s)?.[0] ?? ''
    expect(input).toContain('aria-label=')
  })

  it('los puntitos de aviso de la barra tienen role="img"', () => {
    const src = leer('src/components/TopBar.vue')
    const puntos = [...src.matchAll(/<i [^>]*class="sec-dot"[^>]*>/g)].map((m) => m[0])
    expect(puntos.length).toBeGreaterThan(0)
    for (const p of puntos) expect(p).toContain('role="img"')
  })
})
